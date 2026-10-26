from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    zona_radio_metros = fields.Integer(
        string='Radio de "Consultar zona" (metros)',
        config_parameter='logistic_custom_ivess.zona_radio_metros',
        default=1000,
    )

    @api.constrains('zona_radio_metros')
    def _check_zona_radio_metros(self):
        for rec in self:
            if rec.zona_radio_metros <= 0:
                raise ValidationError(_('El radio de "Consultar zona" tiene que ser mayor que cero.'))

