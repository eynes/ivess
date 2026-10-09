from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    minutos_x_convertir_factura = fields.Float(
        string='Minutos por convertir a factura',
        config_parameter='logistic_custom_ivess.minutos_x_convertir_factura',
    )
    hora_limite_pedidos = fields.Float(
        string='Hora límite de pedidos',
        config_parameter='logistic_custom_ivess.hora_limite_pedidos',
        default=15.0,
    )