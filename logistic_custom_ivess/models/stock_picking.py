from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        self._sync_water_containers()
        return res

    def _sync_water_containers(self):
        WaterContainer = self.env['water.container']
        for picking in self:
            if not picking.partner_id:
                continue
            if picking.picking_type_code not in ('outgoing', 'incoming'):
                continue
            partner = picking.partner_id
            returnable_moves = picking.move_ids.filtered(
                lambda m: m.state == 'done' and m.is_returnable and not m.is_frio_calor and not m.water_container_id
            )
            for move in returnable_moves:
                product_tmpl = move.product_id.product_tmpl_id
                container = WaterContainer.search([
                    ('partner_id', '=', partner.id),
                    ('product_id', '=', product_tmpl.id),
                    ('state', '=', move.container_state)
                ], limit=1)
                if not container:
                    container = WaterContainer.create({
                        'partner_id': partner.id,
                        'product_id': product_tmpl.id,
                        'state': move.container_state,
                    })
                move.water_container_id = container
            if picking.picking_type_code == 'outgoing':
                frio_calor_moves = picking.move_ids.filtered(
                    lambda m: m.state == 'done' and m.is_frio_calor
                )
                for move in frio_calor_moves:
                    product_tmpl = move.product_id.product_tmpl_id
                    for _ in range(int(move.quantity)):
                        WaterContainer.create({
                            'partner_id': partner.id,
                            'product_id': product_tmpl.id,
                            'state': 'asignado',
                            'frio_calor_picking_id': picking.id,
                        })
