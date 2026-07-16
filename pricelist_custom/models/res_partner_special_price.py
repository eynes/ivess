from odoo import fields, models


class ResPartnerSpecialPrice(models.Model):
    _name = 'res.partner.special.price'
    _description = 'Precio Especial de Cliente'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Cliente",
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Producto",
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string="Moneda",
        related='partner_id.company_id.currency_id',
        readonly=True,
        store=True,
    )
    special_price = fields.Monetary(
        string="Precio Especial",
        currency_field='currency_id',
        required=True,
    )
