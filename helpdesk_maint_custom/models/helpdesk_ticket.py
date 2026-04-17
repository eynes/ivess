# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    ticket_source = fields.Selection(
        selection=[('ticket_source', 'Ticket Source')],
        string="Ticket Source",
        default="ticket_source"
    )
    topic = fields.Selection(
        selection=[('topic', 'Topic')],
        string="Topic",
        default='topic'
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
        selection=[('line', 'Line')],
        string="Line",
        default='line'
    )
    maintenance_type = fields.Selection(
        selection=[('maintenance_type', 'Maintenance Type')],
        string="Maintenance Type",
        default='maintenance_type'
    )
