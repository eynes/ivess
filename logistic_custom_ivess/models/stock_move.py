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
