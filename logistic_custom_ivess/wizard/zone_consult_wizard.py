import math
from collections import Counter, defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from ..models.delivery_route import _distancia_km
from ..models.res_partner_distribution import DAY_LABELS_ES

DEFAULT_RADIUS_PARAM = 'logistic_custom_ivess.zona_radio_metros'
DEFAULT_RADIUS = 1000
METERS_PER_DEGREE = 111320.0


def _hora_txt(valor):
    horas, minutos = divmod(round(valor * 60), 60)
    return '%02d:%02d' % (horas, minutos)


class ZoneConsultWizard(models.TransientModel):
    _name = 'zone.consult.wizard'
    _description = 'Consultar zona'

    street = fields.Char(string='Calle')
    number = fields.Char(string='Número')
    city = fields.Char(string='Ciudad')
    state_id = fields.Many2one(
        'res.country.state',
        string='Provincia',
        domain="[('country_id.code', '=', 'AR')]",
        default=lambda self: self._default_state(),
    )
    radius = fields.Integer(
        string='Radio (metros)',
        default=lambda self: self._default_radius(),
    )
    latitude = fields.Float(string='Latitud', digits=(10, 7))
    longitude = fields.Float(string='Longitud', digits=(10, 7))
    searched = fields.Boolean()
    geo_message = fields.Char(readonly=True)
    line_ids = fields.One2many('zone.consult.wizard.line', 'wizard_id', string='Repartos en la zona')
    distribution_ids = fields.Many2many('partner.distribution', string='Clientes en la zona')

    @api.model
    def _default_state(self):
        return self.env['res.country.state'].search(
            [('country_id.code', '=', 'AR'), ('name', '=', 'Buenos Aires')], limit=1,
        )

    @api.model
    def _default_radius(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(DEFAULT_RADIUS_PARAM)
        return int(valor) if valor and valor.isdigit() else DEFAULT_RADIUS

    @api.onchange('street', 'number', 'city', 'state_id')
    def _onchange_address(self):
        # Si cambia la dirección, las coordenadas de la búsqueda anterior ya no valen.
        self.latitude = 0.0
        self.longitude = 0.0
        self.geo_message = False

    def _geolocate(self):
        self.ensure_one()
        argentina = self.env.ref('base.ar')
        calle = ' '.join(p for p in (self.street, self.number) if p)
        try:
            result = self.env['res.partner'].with_context(lang='en_US')._geo_localize(
                calle, '', self.city or '', self.state_id.name or '', argentina.name,
            )
        except UserError as error:
            self.geo_message = str(error)
            return False
        if not result:
            self.geo_message = _(
                'No se encontró la dirección. Cargá la latitud y la longitud a mano y volvé a buscar.'
            )
            return False
        self.latitude, self.longitude = result
        self.geo_message = False
        return True

    def action_search(self):
        self.ensure_one()
        if not (self.street or self.city):
            raise UserError(_('Cargá al menos la calle o la ciudad.'))
        if self.radius <= 0:
            raise UserError(_('El radio tiene que ser mayor que cero.'))
        if not (self.latitude or self.longitude) and not self._geolocate():
            self.line_ids = [(5, 0, 0)]
            self.distribution_ids = [(5, 0, 0)]
            self.searched = False
            return self._reopen()
        self.line_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in self._search_zone()]
        self.searched = True
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _search_zone(self):
        """Una fila por plantilla (reparto + día) con clientes activos dentro del
        radio. Primero se filtra por una caja de latitud/longitud en SQL (usa el
        índice de coordenadas de res.partner) y recién después se calcula la
        distancia real, con la misma función que usa reparto_sugerido."""
        self.ensure_one()
        lat, lon = self.latitude, self.longitude
        radio_km = self.radius / 1000.0
        delta_lat = self.radius / METERS_PER_DEGREE
        delta_lon = self.radius / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
        self.env.cr.execute(SQL(
            """
            SELECT pd.id, tdr.id, rp.id, rp.partner_latitude, rp.partner_longitude,
                   rp.average_hour, rp.visit_hour_from, rp.visit_hour_to
              FROM res_partner rp
              JOIN partner_distribution pd ON pd.partner_id = rp.id
              JOIN template_delivery_route tdr ON tdr.id = pd.distribution
              JOIN delivery_route_number drn ON drn.id = tdr.delivery_number_id
             WHERE rp.partner_latitude BETWEEN %s AND %s
               AND rp.partner_longitude BETWEEN %s AND %s
               AND rp.active
               AND NOT drn.is_technical_delivery
               AND (rp.company_id IS NULL OR rp.company_id IN %s)
            """,
            lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon,
            tuple(self.env.companies.ids) or (0,),
        ))
        por_plantilla = defaultdict(list)
        distribution_ids = []
        for dist_id, plantilla_id, _partner, la, lo, promedio, desde, hasta in self.env.cr.fetchall():
            distancia = _distancia_km((lat, lon), (la, lo))
            if distancia <= radio_km:
                por_plantilla[plantilla_id].append((distancia, promedio, desde, hasta))
                distribution_ids.append(dist_id)
        self.distribution_ids = [(6, 0, distribution_ids)]

        plantillas = {t.id: t for t in self.env['template.delivery.route'].browse(list(por_plantilla))}
        filas = []
        for plantilla_id, clientes in por_plantilla.items():
            plantilla = plantillas[plantilla_id]
            horas = [h for _d, h, _f, _t in clientes if h]
            franjas = Counter((f, t) for _d, _h, f, t in clientes if f or t)
            franja = franjas.most_common(1)[0][0] if franjas else False
            filas.append({
                'template_id': plantilla_id,
                'client_count': len(clientes),
                'distance_m': round(min(c[0] for c in clientes) * 1000),
                'average_hour': sum(horas) / len(horas) if horas else 0.0,
                'time_window': self._franja_txt(*franja) if franja else False,
            })
        return sorted(filas, key=lambda f: f['distance_m'])

    @staticmethod
    def _franja_txt(desde, hasta):
        if desde and hasta:
            return '%s a %s' % (_hora_txt(desde), _hora_txt(hasta))
        return ('desde %s' % _hora_txt(desde)) if desde else ('hasta %s' % _hora_txt(hasta))

    def action_view_map(self):
        self.ensure_one()
        if not self.distribution_ids:
            raise UserError(_('No hay clientes en la zona para mostrar en el mapa.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clientes cerca de %s') % ' '.join(p for p in (self.street, self.number) if p),
            'res_model': 'partner.distribution',
            'view_mode': 'map,list',
            'views': [
                (self.env.ref('logistic_custom_ivess.view_partner_distribution_reparto_map').id, 'map'),
                (self.env.ref('logistic_custom_ivess.view_partner_distribution_reparto_list').id, 'list'),
            ],
            'search_view_id': [self.env.ref('logistic_custom_ivess.view_partner_distribution_reparto_search').id],
            'domain': [('id', 'in', self.distribution_ids.ids)],
        }


class ZoneConsultWizardLine(models.TransientModel):
    _name = 'zone.consult.wizard.line'
    _description = 'Consultar zona: reparto en la zona'
    _order = 'distance_m, id'

    wizard_id = fields.Many2one('zone.consult.wizard', required=True, ondelete='cascade')
    template_id = fields.Many2one('template.delivery.route', string='Plantilla')
    delivery_number_id = fields.Many2one(
        related='template_id.delivery_number_id',
        string='Reparto',
    )
    visit_day = fields.Char(string='Día', compute='_compute_visit_day')
    client_count = fields.Integer(string='Clientes en el radio')
    distance_m = fields.Integer(string='Distancia al más cercano (m)')
    average_hour = fields.Float(string='Hora promedio', digits=(16, 2))
    average_hour_txt = fields.Char(string='Hora promedio de visita', compute='_compute_average_hour_txt')
    time_window = fields.Char(string='Franja habitual')

    @api.depends('template_id.day')
    def _compute_visit_day(self):
        for line in self:
            dia = line.template_id.day
            line.visit_day = DAY_LABELS_ES.get(dia, dia) or False

    @api.depends('average_hour')
    def _compute_average_hour_txt(self):
        for line in self:
            line.average_hour_txt = _hora_txt(line.average_hour) if line.average_hour else False
