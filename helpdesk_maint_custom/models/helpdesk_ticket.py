# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models, _


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    use_maintenance_orders = fields.Boolean(related='team_id.use_maintenance_orders')
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

    def action_create_maintenance_order(self):
        self.ensure_one()
        clean_ctx = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        order = self.env['maintenance.request'].with_context(clean_ctx).create({
            'name': self.name,
            'ticket_id': self.id,
            'company_id': self.company_id.id,
            'description': self.description,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Order'),
            'res_model': 'maintenance.request',
            'view_mode': 'form',
            'res_id': order.id,
        }

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
