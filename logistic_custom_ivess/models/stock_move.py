from odoo import models, fields


class StockMove(models.Model):
    _inherit = 'stock.move'

    water_container_id = fields.Many2one(
        'water.container',
        string='Envase',
    )
    container_state_id = fields.Many2one(
        'water.container.state',
        string='Estado del Envase',
    )
    is_returnable = fields.Boolean(
        related='product_id.product_tmpl_id.is_returnable',
        store=True,
        string='Es Retornable',
    )
