# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import SQL
from odoo.tools.misc import formatLang

from .delivery_route import _distancia_km

FREQUENCY_MAPPING = {
    'weekly': 1,
    'biweekly': 2,
    'monthly': 4,
}

DAY_LABELS_ES = {
    'monday': 'Lunes',
    'tuesday': 'Martes',
    'wednesday': 'Miércoles',
    'thursday': 'Jueves',
    'friday': 'Viernes',
    'saturday': 'Sábado',
    'sunday': 'Domingo',
}


class PartnerDistributions(models.Model):
    _name = 'partner.distribution'
    _inherit = ['visit.schedule.mixin']
    _description = 'Distributions'

    distribution = fields.Many2one('template.delivery.route')
    visit_day = fields.Selection(
        related='distribution.day',
        string='Visit Day',
    )
    frequency = fields.Selection(
        selection=[
            ('weekly', 'Weekly'),
            ('biweekly', 'Biweekly'),
            ('monthly', 'Monthly')
        ],
        default=False,
        string='Frequency',
    )
    partner_id = fields.Many2one('res.partner', string='Partner')
    reparto_sugerido = fields.Char(
        string='Sugerencia por ubicación',
        compute='_compute_reparto_sugerido',
    )
    dias_sugeridos = fields.Char(
        string='Días más cercanos',
        compute='_compute_dias_sugeridos',
    )

    @api.depends('partner_id')
    def _compute_reparto_sugerido(self):
        for rec in self:
            rec.reparto_sugerido = rec._sugerir_reparto() if not rec._origin.id else False

    @api.depends('partner_id', 'distribution')
    def _compute_dias_sugeridos(self):
        for rec in self:
            rec.dias_sugeridos = rec._sugerir_dias()

    def _sugerir_dias(self):
        """Minuta del 01/10/2026 (cambio de día): los 3 días del mismo reparto
        cuyos clientes están más cerca del cliente, sin contar los días en que
        ya lo visitan. Misma medida que _sugerir_reparto: promedio de las 3
        distancias más cortas. Es solo un texto de ayuda."""
        self.ensure_one()
        partner = self.partner_id
        reparto = self.distribution.delivery_number_id
        lat, lon = partner.partner_latitude, partner.partner_longitude
        if not reparto or not (lat or lon):
            return False
        partner_id = partner._origin.id or 0
        self.env.cr.execute(SQL(
            """
            SELECT tdr.id, rp.partner_latitude, rp.partner_longitude
              FROM delivery_route_line drl
              JOIN template_delivery_route tdr ON tdr.id = drl.template_route_id
              JOIN res_partner rp ON rp.id = drl.client_id
             WHERE drl.route_id IS NULL
               AND tdr.delivery_number_id = %s
               AND rp.active
               AND rp.id != %s
               AND (rp.partner_latitude != 0 OR rp.partner_longitude != 0)
               AND tdr.day NOT IN (
                       SELECT actual.day
                         FROM partner_distribution pd
                         JOIN template_delivery_route actual ON actual.id = pd.distribution
                        WHERE pd.partner_id = %s)
            """,
            reparto.id, partner_id, partner_id,
        ))
        distancias = defaultdict(list)
        for plantilla_id, la, lo in self.env.cr.fetchall():
            distancias[plantilla_id].append(_distancia_km((lat, lon), (la, lo)))
        if not distancias:
            return False
        puntaje = {p: sum(sorted(d)[:3]) / len(d[:3]) for p, d in distancias.items()}
        plantillas = self.env['template.delivery.route'].browse(sorted(puntaje, key=puntaje.get)[:3])
        return _('En el reparto %(reparto)s: %(dias)s.') % {
            'reparto': reparto.display_name,
            'dias': ', '.join(
                '%s %s (%s km)' % (
                    plantilla.name,
                    DAY_LABELS_ES.get(plantilla.day, plantilla.day).lower(),
                    formatLang(self.env, puntaje[plantilla.id], digits=1),
                )
                for plantilla in plantillas
            ),
        }

    def _sugerir_reparto(self):
        """Reparto cuyos clientes (en las plantillas) están más cerca del cliente:
        promedio de las 3 distancias más cortas. Es solo un texto de ayuda."""
        self.ensure_one()
        partner = self.partner_id
        lat, lon = partner.partner_latitude, partner.partner_longitude
        if not (lat or lon):
            return False
        filas = []
        for radio in (0.02, 0.1):  # grados: ~2 km y ~10 km
            self.env.cr.execute(SQL(
                """
                SELECT DISTINCT tdr.delivery_number_id, rp.id, rp.partner_latitude, rp.partner_longitude
                  FROM delivery_route_line drl
                  JOIN template_delivery_route tdr ON tdr.id = drl.template_route_id
                  JOIN res_partner rp ON rp.id = drl.client_id
                 WHERE drl.route_id IS NULL
                   AND tdr.delivery_number_id IS NOT NULL
                   AND rp.active
                   AND rp.id != %s
                   AND rp.partner_latitude BETWEEN %s AND %s
                   AND rp.partner_longitude BETWEEN %s AND %s
                """,
                partner._origin.id or 0, lat - radio, lat + radio, lon - radio, lon + radio,
            ))
            filas = self.env.cr.fetchall()
            if filas:
                break
        if not filas:
            return False
        distancias = defaultdict(list)
        # DISTINCT: un cliente con varios días de visita cuenta una sola vez.
        for numero_id, _cliente_id, la, lo in filas:
            distancias[numero_id].append(_distancia_km((lat, lon), (la, lo)))
        puntaje = {n: sum(sorted(d)[:3]) / len(sorted(d)[:3]) for n, d in distancias.items()}
        mejor = min(puntaje, key=puntaje.get)
        return _('Reparto %(reparto)s: sus clientes más cercanos están a %(km)s km.') % {
            'reparto': self.env['delivery.route.number'].browse(mejor).display_name,
            'km': formatLang(self.env, puntaje[mejor], digits=1),
        }

    message_ids = fields.One2many(
        'partner.distribution.message',
        'partner_distribution_id',
        string='Mensajes',
    )

    def _get_target_route(self):
        self.ensure_one()
        if not self.distribution or not self.partner_id:
            return self.env['delivery.route']
        today = fields.Date.today()
        route = self.env['delivery.route'].search([
            ('template_delivery_route_id', '=', self.distribution.id),
            ('state', '=', 'in_progress'),
            ('delivery_route_line_ids.client_id', '=', self.partner_id.id),
        ], order='delivery_date desc', limit=1)
        if route:
            return route
        return self.env['delivery.route'].search([
            ('template_delivery_route_id', '=', self.distribution.id),
            ('state', 'in', ('draft', 'sincronizado')),
            ('delivery_date', '>=', today),
            ('delivery_route_line_ids.client_id', '=', self.partner_id.id),
        ], order='delivery_date asc', limit=1)

    def action_open_message_wizard(self):
        self.ensure_one()
        if not self._get_target_route():
            raise ValidationError(_(
                "No hay un recorrido en curso ni programado para la plantilla %(template)s. "
                "No se puede asociar un mensaje."
            ) % {'template': self.distribution.name})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mensaje',
            'res_model': 'res.partner.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }
    route_line_id = fields.Many2one(
        'delivery.route.line',
        string='Route Line',
        ondelete='set null',
        copy=False,
    )
    last_visit_date = fields.Date(
        string='Última Visita',
        copy=False,
        readonly=True,
    )

    @api.constrains('partner_id', 'distribution')
    def _check_unique_visit_day(self):
        for record in self:
            if not record.partner_id or not record.distribution or not record.distribution.day:
                continue
            duplicate = self.search([
                ('id', '!=', record.id),
                ('partner_id', '=', record.partner_id.id),
                ('distribution.day', '=', record.distribution.day),
            ], limit=1)
            if duplicate:
                day_label = DAY_LABELS_ES.get(record.distribution.day, record.distribution.day)
                raise ValidationError(_(
                    "El cliente %(partner)s ya tiene asignada una distribución los días %(day)s "
                    "(plantilla %(template)s). No puede tener dos líneas con el mismo día de visita."
                ) % {
                    'partner': record.partner_id.name,
                    'day': day_label,
                    'template': duplicate.distribution.name,
                })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.distribution and record.partner_id:
                record._process_template_line()
                record._process_delivery_routes()
        return records

    def write(self, vals):
        old_vals = {
            rec.id: {
                'distribution': rec.distribution.id,
                'frequency': rec.frequency,
            }
            for rec in self
        }
        res = super().write(vals)
        if 'distribution' in vals or 'frequency' in vals:
            for record in self:
                old = old_vals[record.id]
                distribution_changed = 'distribution' in vals and (vals.get('distribution') or False) != old['distribution']
                frequency_changed = 'frequency' in vals

                if distribution_changed:
                    if old['distribution']:
                        self.env['delivery.route.line'].search([
                            ('template_route_id', '=', old['distribution']),
                            ('client_id', '=', record.partner_id.id),
                            ('route_id', '=', False),
                        ]).unlink()
                        record._unlink_future_route_lines(old['distribution'])
                    if record.distribution and record.partner_id:
                        record._process_template_line()
                        record._process_delivery_routes()
                elif frequency_changed and record.distribution:
                    record._unlink_future_route_lines(record.distribution.id)
                    record._process_delivery_routes()
        return res

    def unlink(self):
        for record in self:
            if record.distribution and record.partner_id:
                record._unlink_future_route_lines(record.distribution.id)
        route_lines = self.mapped('route_line_id')
        res = super().unlink()
        if not self.env.context.get('no_sync_distribution'):
            route_lines.with_context(no_sync_distribution=True).unlink()
        return res

    def _process_template_line(self):
        self.ensure_one()
        existing = self.distribution.delivery_route_line_ids.filtered(
            lambda l: l.client_id.id == self.partner_id.id and not l.route_id
        )
        if existing:
            self.route_line_id = existing[0].id
            return
        line = self.env['delivery.route.line'].create({
            'template_route_id': self.distribution.id,
            'client_id': self.partner_id.id,
        })
        self.route_line_id = line.id

    def _process_delivery_routes(self):
        self.ensure_one()
        if not self.distribution or not self.partner_id or not self.frequency:
            return

        today = fields.Date.today()
        filtered_routes = self.env['delivery.route'].search([
            ('delivery_date', '>', today),
            ('template_delivery_route_id', '=', self.distribution.id),
        ], order='delivery_date')
        route_dates = sorted(r.delivery_date for r in filtered_routes)

        monthly_dates = defaultdict(list)
        for date in route_dates:
            monthly_dates[date.strftime('%Y-%m')].append(date)

        interval = FREQUENCY_MAPPING.get(self.frequency, 1)
        if self.frequency == 'monthly':
            selected_dates = [dates[0] for dates in monthly_dates.values()]
        else:
            selected_dates = route_dates[::interval]

        for route in filtered_routes.filtered(lambda r: r.delivery_date in selected_dates):
            rastrillo_exists = any(
                l.client_id.id == self.partner_id.id and l.origin == 'rastrillo'
                for l in route.delivery_route_line_ids
            )
            if rastrillo_exists:
                continue
            new_line = self.env['delivery.route.line'].create({
                'client_id': self.partner_id.id,
                'origin': 'plantilla',
            })
            route.delivery_route_line_ids = [(4, new_line.id)]

    def _unlink_future_route_lines(self, distribution_id):
        self.ensure_one()
        today = fields.Date.today()
        self.env['delivery.route.line'].search([
            ('client_id', '=', self.partner_id.id),
            ('route_id.delivery_date', '>', today),
            ('route_id.template_delivery_route_id', '=', distribution_id),
        ]).unlink()


class PartnerDistributionMessage(models.Model):
    _name = 'partner.distribution.message'
    _description = 'Mensaje de Distribución por Recorrido'

    partner_distribution_id = fields.Many2one(
        'partner.distribution',
        string='Distribución',
        required=True,
        ondelete='cascade',
        index=True,
    )
    route_id = fields.Many2one(
        'delivery.route',
        string='Recorrido',
        required=True,
        ondelete='cascade',
        index=True,
    )
    route_line_id = fields.Many2one(
        'delivery.route.line',
        string='Línea de Recorrido',
        compute='_compute_route_line_id',
        store=True,
        index=True,
    )
    message_text = fields.Text(
        string='Mensaje',
    )

    _sql_constraints = [
        (
            'partner_distribution_route_uniq',
            'unique(partner_distribution_id, route_id)',
            'Ya existe un mensaje para este recorrido en esta distribución.',
        ),
    ]

    @api.depends('route_id', 'partner_distribution_id.partner_id')
    def _compute_route_line_id(self):
        for message in self:
            partner = message.partner_distribution_id.partner_id
            if not message.route_id or not partner:
                message.route_line_id = False
                continue
            message.route_line_id = self.env['delivery.route.line'].search([
                ('route_id', '=', message.route_id.id),
                ('client_id', '=', partner.id),
            ], limit=1)
