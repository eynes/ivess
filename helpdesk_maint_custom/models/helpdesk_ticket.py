# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

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
