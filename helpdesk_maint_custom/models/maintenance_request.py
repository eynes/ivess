# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Helpdesk Ticket',
        index=True,
    )
    material_ids = fields.One2many(
        'maintenance.request.material',
        'request_id',
        string='Materials',
        copy=True,
    )
