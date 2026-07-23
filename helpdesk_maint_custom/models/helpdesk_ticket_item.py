# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class HelpdeskTicketItem(models.Model):
    _name = "helpdesk.ticket.item"
    _description = "Ítem de ticket de taller mecánico"

    ticket_id = fields.Many2one("helpdesk.ticket", required=True, ondelete="cascade")
    name = fields.Char(string="Descripción", required=True)
    value = fields.Char(string="Estado")
