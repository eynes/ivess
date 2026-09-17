# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models, _


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    use_maintenance_orders = fields.Boolean(related='team_id.use_maintenance_orders')
    team_type = fields.Selection(related='team_id.team_type')
    maintenance_order_ids = fields.One2many('maintenance.request', 'ticket_id', copy=False)
    maintenance_orders_count = fields.Integer(
        string='Maintenance Orders Count',
        compute='_compute_maintenance_orders_count',
        compute_sudo=True,
    )

    @api.depends('maintenance_order_ids')
    def _compute_maintenance_orders_count(self):
        data = self.env['maintenance.request'].sudo()._read_group(
            [('ticket_id', 'in', self.ids)], ['ticket_id'], ['__count']
        )
        mapped = {ticket.id: count for ticket, count in data}
        for ticket in self:
            ticket.maintenance_orders_count = mapped.get(ticket.id, 0)

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        tickets = super().create(vals_list)
        for ticket in tickets:
            if ticket.use_maintenance_orders:
                ticket._auto_create_maintenance_order()
        return tickets

    def _get_maintenance_order_values(self):
        self.ensure_one()
        vals = {
            'name': self.name,
            'ticket_id': self.id,
            'company_id': self.company_id.id,
            'description': self.description,
            'item_ids': self._get_maintenance_order_item_values(),
        }
        forced_team_id = self.env.context.get('maintenance_team_id_ctx')
        if forced_team_id:
            vals['maintenance_team_id'] = forced_team_id
        return vals

    def _auto_create_maintenance_order(self):
        self.ensure_one()
        clean_ctx = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        self.env['maintenance.request'].with_context(clean_ctx).create(
            self._get_maintenance_order_values()
        )

    def action_create_maintenance_order(self):
        self.ensure_one()
        clean_ctx = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        order = self.env['maintenance.request'].with_context(clean_ctx).create(
            self._get_maintenance_order_values()
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Order'),
            'res_model': 'maintenance.request',
            'view_mode': 'form',
            'res_id': order.id,
        }

    def _get_maintenance_order_item_values(self):
        self.ensure_one()
        return [
            (0, 0, {'name': item.name, 'value': item.value})
            for item in self.item_ids
        ]

    def _sync_maintenance_order_items(self):
        for ticket in self:
            if not ticket.maintenance_order_ids:
                continue
            item_values = ticket._get_maintenance_order_item_values()
            for order in ticket.maintenance_order_ids:
                order.write({'item_ids': [(5, 0, 0)] + item_values})

    def action_view_maintenance_orders(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Orders'),
            'res_model': 'maintenance.request',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {
                'default_ticket_id': self.id,
                'default_company_id': self.company_id.id,
                'default_name': self.name,
            },
        }
        if self.maintenance_orders_count == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.maintenance_order_ids.id,
            })
        return action

    ticket_source = fields.Selection(
        selection=[
            ('phone', 'Teléfono'),
            ('email', 'Email'),
            ('web', 'Web'),
            ('other', 'Otro')
        ],
        string="Ticket Source",
        default="web"
    )
    topic = fields.Selection(
        selection=[
            ('general_inquiry', 'Consulta general'),
            ('report_problem', 'Informar un problema'),
            ('building_problem', 'Informar un problema / Edilicio'),
            ('industrial_problem', 'Informar un problema / Industrial'),
            ('order', 'Pedido'),
            ('suggestions', 'Sugerencias')
        ],
        string="Ticket",
        default='general_inquiry'
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        string="Department",
    )
    due_date = fields.Date(string="Due Date")
    require_signature = fields.Boolean(string="Requires Signature")
    signature = fields.Binary(string="Signature", attachment=True)
    internal_note = fields.Text(string="Internal Note")
    line = fields.Selection(
        selection=[
            ('siphons_line', 'Línea Sifones'),
            ('cold_heat', 'Frío/Calor'),
            ('lavazza', 'Lavazza'),
            ('building_plant', 'Edificio Planta'),
            ('positive_impact', 'Impacto positivo'),
            ('la_plata', 'La Plata'),
            ('bottled_line', 'Línea Botellones'),
            ('nafa', 'Nafa'),
            ('auxiliary_services', 'Servicios Auxiliares'),
            ('mechanical_workshop', 'Taller mecánico'),
            ('water_treatment', 'Tratamiento de agua'),
        ],
        string="Line",
    )
    maintenance_type = fields.Selection(
        selection=[
            ('corrective', 'Correctivo'),
            ('preventive', 'Preventivo')
        ],
        string="Maintenance Type",
        default='corrective'
    )

    item_ids = fields.One2many("helpdesk.ticket.item", "ticket_id", string="Ítems")

    # Workshop (Taller Mecánico) fields
    intake_user = fields.Char(string="Usuario JMobile")
    dispatch_id = fields.Many2one("delivery.route.number", string="Reparto")
    dispatch = fields.Char(string="Reparto (texto)")
    webhub_dispatch = fields.Char(string="Reparto Webhub")
    driver_name = fields.Char(string="Nombre")
    vehicle_model = fields.Char(string="Modelo")
    webhub_vehicle_model = fields.Char(string="Modelo Webhub")
    equipment_id = fields.Many2one("maintenance.equipment", string="Equipo")
    vehicle_location = fields.Char(string="Ubicación")
    breakdown_reason = fields.Char(string="Motivo de auxilio")
    maps_location = fields.Char(string="Ubicación Maps")
    webhub_description = fields.Char(string="WebHub Descripción")
    warehouse_id = fields.Many2one('stock.warehouse', string="Planta")
    intake_payload = fields.Html(string="Payload de ingreso", readonly=True, sanitize=False)

    # Chatbot WhatsApp (T16556): tipo de solicitud e idempotencia comunes
    # a los 4 servicios de intake (checklist, novedad, auxilio, siniestro).
    workshop_request_type = fields.Selection(
        selection=[
            ('checklist', 'Checklist jMobile'),
            ('news', 'Novedad'),
            ('breakdown', 'Auxilio'),
            ('accident', 'Siniestro'),
        ],
        string="Tipo de solicitud",
        index=True,
    )
    intake_external_id = fields.Char(
        string="ID externo de intake",
        index=True,
        copy=False,
        readonly=True,
        help="ID del envío en el chatbot, usado para no duplicar tickets ante reintentos.",
    )

    # Siniestro (workshop_request_type = accident)
    accident_business_unit = fields.Char(string="Unidad de negocio")
    driver_file_number = fields.Char(string="Legajo")
    driver_identification = fields.Char(string="DNI del conductor")
    driver_address = fields.Char(string="Dirección del conductor")
    accident_vehicle_damage = fields.Text(string="Daños del vehículo")
    accident_facts = fields.Text(string="Descripción de los hechos")
    third_party_name = fields.Char(string="Nombre y apellido del tercero")
    third_party_vehicle = fields.Char(string="Vehículo del tercero")
    third_party_plate = fields.Char(string="Patente del tercero")
    third_party_identification = fields.Char(string="DNI del tercero")
    third_party_phone = fields.Char(string="Contacto del tercero")
    third_party_insurer = fields.Char(string="Compañía de seguro del tercero")
    third_party_vehicle_damage = fields.Text(string="Daños del vehículo del tercero")
    accident_date = fields.Date(string="Fecha del siniestro")
    accident_time = fields.Float(string="Hora del siniestro")
    accident_address = fields.Char(string="Dirección del siniestro")
    accident_city = fields.Char(string="Localidad del siniestro")
    accident_notes = fields.Text(string="Observaciones del siniestro")

    # Recargas (team_type = refill, workshop_request_type no aplica: no es taller)
    refill_type = fields.Selection(
        selection=[
            ('factory', 'Recarga Fábrica'),
            ('street', 'Recarga en Calle'),
        ],
        string="Tipo de recarga",
    )
    refill_to_dispatch = fields.Char(string="Hacia el reparto (texto)")
    refill_to_dispatch_id = fields.Many2one("delivery.route.number", string="Hacia el reparto")
