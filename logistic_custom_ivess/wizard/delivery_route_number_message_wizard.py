# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DeliveryRouteNumberMessageWizard(models.TransientModel):
    _name = 'delivery.route.number.message.wizard'
    _description = 'Wizard Mensaje General por Reparto'

    delivery_route_number_ids = fields.Many2many(
        'delivery.route.number',
        string='Reparto',
    )
    message_text = fields.Text(
        string='Mensaje',
    )
    apply_to_all = fields.Boolean(
        string='Todos / Aplicar a todos',
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.apply_to_all and not self.delivery_route_number_ids:
            raise UserError(_(
                "Debe seleccionar al menos un reparto o marcar 'Todos / Aplicar a todos'."
            ))
        self.env['delivery.route.number.message'].create({
            'delivery_route_number_ids': [(6, 0, self.delivery_route_number_ids.ids)],
            'message_text': self.message_text,
            'apply_to_all': self.apply_to_all,
        })
        return {'type': 'ir.actions.act_window_close'}
