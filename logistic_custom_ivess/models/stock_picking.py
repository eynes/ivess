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
            returnable_moves = picking.move_ids.filtered(
                lambda m: m.state == 'done' and m.is_returnable and not m.water_container_id
            )
            for move in returnable_moves:
                product_tmpl = move.product_id.product_tmpl_id
                partner = picking.partner_id
                container = WaterContainer.search([
                    ('partner_id', '=', partner.id),
                    ('product_id', '=', product_tmpl.id),
                ], limit=1)
                if not container:
                    container = WaterContainer.create({
                        'partner_id': partner.id,
                        'product_id': product_tmpl.id,
                        'assignment_date': fields.Date.today(),
                        'state': 'prestado',
                    })
                move.water_container_id = container
