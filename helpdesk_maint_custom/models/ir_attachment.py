# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _sync_to_maintenance_requests(self):
        ticket_attachments = self.filtered(
            lambda a: a.res_model == 'helpdesk.ticket' and a.res_id
        )
        if not ticket_attachments:
            return

        ticket_ids = ticket_attachments.mapped('res_id')
        tickets = self.env['helpdesk.ticket'].browse(ticket_ids)

        for ticket in tickets:
            if not ticket.maintenance_order_ids:
                continue
            attachments = ticket_attachments.filtered(lambda a: a.res_id == ticket.id)
            for order in ticket.maintenance_order_ids:
                existing = self.search([
                    ('res_model', '=', 'maintenance.request'),
                    ('res_id', '=', order.id),
                    ('name', 'in', attachments.mapped('name')),
                ])
                existing_names = existing.mapped('name')
                for attachment in attachments:
                    if attachment.name not in existing_names:
                        attachment.copy({
                            'res_model': 'maintenance.request',
                            'res_id': order.id,
                        })

    def create(self, vals_list):
        attachments = super().create(vals_list)
        attachments._sync_to_maintenance_requests()
        return attachments
