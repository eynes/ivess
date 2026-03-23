# Copyright 2018 Creu Blanca
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockRequestOrder(models.Model):
    _inherit = "stock.request.order"
    _description = "Stock Request Order"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        location = None
        if self.env.user.location_id:
            location = self.env.user.location_id
        if location:
            res["warehouse_id"] = False
            res["location_id"] = location.id
        route_param = self.env['ir.config_parameter'].sudo().get_param('custom_ivess_product.manually_set_route_id')
        if route_param:
            try:
                res["route_id"] = int(route_param)
            except (ValueError, TypeError):
                pass
        return res

    def action_open_note_wizard(self):
        self.ensure_one()

        template = self.env['mail.template'].search([
            ('is_default_for_stock_request', '=', True),
            ('model', '=', 'stock.request.order')
        ], limit=1)

        ctx = {
            'default_model': 'stock.request.order',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_subtype_xmlid': 'mail.mt_note',
        }

        if template:
            ctx['default_use_template'] = True
            ctx['default_template_id'] = template.id
        return {
            'name': 'Registrar una nota',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'target': 'new',
            'context': ctx,
        }

class StockRequest(models.Model):
    _inherit = "stock.request"

    def _action_confirm(self):
        res = super()._action_confirm()
        if self.location_id:
            pickings = self.picking_ids
            if pickings:
                pickings.write({
                    'location_dest_id': self.location_id.id,
                    'manual_location': True
                })
                pickings.move_ids.write(
                    {'location_dest_id': self.location_id.id}
                )
                if pickings.move_line_ids:
                    pickings.move_line_ids.write(
                        {'location_dest_id': self.location_id.id}
                    )
        return res

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    manual_location = fields.Boolean(readonly=True)

    @api.depends('picking_type_id', 'partner_id', 'manual_location')
    def _compute_location_id(self):
        manual_pickings = self.filtered(lambda p: p.manual_location)
        standard_pickings = self - manual_pickings
        if standard_pickings:
            super(StockPicking, standard_pickings)._compute_location_id()
