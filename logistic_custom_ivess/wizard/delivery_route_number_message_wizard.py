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
    route_ids = fields.Many2many(
        'delivery.route',
        string='Recorrido',
        compute='_compute_route_ids',
        readonly=True,
    )
    message_text = fields.Text(
        string='Mensaje',
    )
    apply_to_all = fields.Boolean(
        string='Todos / Aplicar a todos',
        help="Si se marca, el mensaje se aplicará a todos los repartos existentes.",
    )

    @api.depends('apply_to_all', 'delivery_route_number_ids')
    def _compute_route_ids(self):
        for wizard in self:
            numbers = (
                self.env['delivery.route.number'].search([])
                if wizard.apply_to_all
                else wizard.delivery_route_number_ids
            )
            routes = self.env['delivery.route']
            for number in numbers:
                routes |= number._get_target_route()
            wizard.route_ids = routes

    def action_confirm(self):
        self.ensure_one()
        if not self.apply_to_all and not self.delivery_route_number_ids:
            raise UserError(_(
                "Debe seleccionar al menos un reparto o marcar 'Todos / Aplicar a todos'."
            ))
        if not self.route_ids:
            raise UserError(_(
                "No hay ningún recorrido en curso ni programado para el/los reparto(s) seleccionado(s). "
                "No se puede asociar un mensaje."
            ))
        self.env['delivery.route.number.message'].create({
            'delivery_route_number_ids': [(6, 0, self.delivery_route_number_ids.ids)],
            'route_ids': [(6, 0, self.route_ids.ids)],
            'message_text': self.message_text,
            'apply_to_all': self.apply_to_all,
        })
        return {'type': 'ir.actions.act_window_close'}
