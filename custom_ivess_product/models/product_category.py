from odoo import models, fields, _


class ProductCategory(models.Model):
    _inherit = 'product.category'

    new_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='New Product Sequence', # Es buena práctica agregar el string
        help='Sequence to use for new products.', # Texto plano, sin _()
        copy=False,
        required=True,
    )

    repaired_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Repaired Product Sequence',
        help='Sequence to use for repaired products', # Texto plano, sin _()
        copy=False,
        required=True,
    )
