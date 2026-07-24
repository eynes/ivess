# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class MaintenanceRequestItem(models.Model):
    _name = "maintenance.request.item"
    _description = "Ítem de orden de mantenimiento"

    request_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade")
    name = fields.Char(string="Descripción", required=True)
    value = fields.Char(string="Estado")
