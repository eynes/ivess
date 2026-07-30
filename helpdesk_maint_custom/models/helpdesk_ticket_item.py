# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models


class HelpdeskTicketItem(models.Model):
    _name = "helpdesk.ticket.item"
    _description = "Ítem de ticket de taller mecánico"

    ticket_id = fields.Many2one("helpdesk.ticket", required=True, ondelete="cascade")
    name = fields.Char(string="Descripción", required=True)
    value = fields.Char(string="Estado")

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items.ticket_id._sync_maintenance_order_items()
        return items

    def write(self, vals):
        res = super().write(vals)
        self.ticket_id._sync_maintenance_order_items()
        return res

    def unlink(self):
        tickets = self.ticket_id
        res = super().unlink()
        tickets._sync_maintenance_order_items()
        return res
