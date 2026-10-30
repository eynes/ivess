from odoo import models, fields, api
from .water_container import STATE_SELECTION


class StockMove(models.Model):
    _inherit = 'stock.move'

    water_container_id = fields.Many2one(
        'water.container',
        string='Envase',
    )
    container_state = fields.Selection(
        STATE_SELECTION,
        string='Estado del Envase',
    )
    is_returnable = fields.Boolean(
        related='product_id.product_tmpl_id.is_returnable',
        store=True,
        string='Es Retornable',
    )
    is_frio_calor = fields.Boolean(
        related='product_id.product_tmpl_id.is_frio_calor',
        store=True,
        string='Es Frio/Calor',
    )

    @api.onchange('water_container_id')
    def _onchange_water_container_id(self):
        self.container_state = self.water_container_id.state if self.water_container_id else False

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        # Moves del mismo producto con distinto estado de envase no se fusionan:
        # _sync_water_containers usa el estado de cada move para elegir el envase.
        return super()._prepare_merge_moves_distinct_fields() + ['container_state']

    def _action_assign(self, force_qty=False):
        res = super()._action_assign(force_qty=force_qty)
        
        serial_moves = self.filtered(
            lambda m: m.has_tracking == 'serial'
            and m.sale_line_id.serial_lot_ids
            and m.state not in ('done', 'cancel')
            and not m.picked
        )
        
        for move in serial_moves:
            requested = move.sale_line_id.serial_lot_ids

            # Series pedidas con stock libre en la ubicacion del move
            quants_in_location = self.env['stock.quant']._gather(move.product_id, move.location_id)
            free_quants = quants_in_location.filtered(
                lambda q: q.lot_id in requested and q.available_quantity > 0
            )
            free_lots = free_quants.lot_id

            # Series pedidas que este move ya reservo: no figuran como libres
            reserved_lots = requested & move.move_line_ids.lot_id

            available = free_lots | reserved_lots
            if set(available.ids) != set(move.lot_ids.ids):
                move.lot_ids = available
                move._recompute_state()
        return res
