from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_discount_percentage = fields.Float(
        string="% de Descuento",
        digits=(5, 2),
        default=0.0,
    )
    special_price_ids = fields.One2many(
        comodel_name='res.partner.special.price',
        inverse_name='partner_id',
        string="Precios Especiales",
    )

    @api.constrains('customer_discount_percentage')
    def _check_discount_range(self):
        for rec in self:
            if not (0.0 <= rec.customer_discount_percentage <= 100.0):
                raise ValidationError(
                    'El porcentaje de descuento debe estar entre 0 y 100.'
                )
