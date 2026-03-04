from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # 'config_parameter' hace que se guarde automáticamente en ir.config_parameter
    manually_set_route_id = fields.Many2one(
        'stock.route',
        string="Ruta de Reabastecimiento por Defecto",
        config_parameter='custom_ivess_product.manually_set_route_id'
    )
