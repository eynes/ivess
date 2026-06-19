from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    free_of_charge = fields.Boolean(
        default=False,
        string='Sin Cargo',
    )

    @api.constrains('free_of_charge', 'product_id')
    def _check_free_of_charge(self):
        for line in self:
            if line.free_of_charge and not line.product_id.product_tmpl_id.allow_free_of_charge:
                raise ValidationError(_(
                    'El producto "%s" no permite ser marcado como Sin Cargo.'
                ) % line.product_id.display_name)

    @api.onchange('product_id')
    def _onchange_product_id_free_of_charge(self):
        if self.free_of_charge and not self.product_id.product_tmpl_id.allow_free_of_charge:
            self.free_of_charge = False
