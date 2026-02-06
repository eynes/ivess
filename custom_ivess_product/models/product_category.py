from odoo import models, fields, _


class ProductCategory(models.Model):
    _inherit = 'product.category'

    new_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        help=_('Sequence to use for new products.'),
        copy=False,
        required=True,
    )
    repaired_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        help=_('Sequence to use for repaired products'),
        copy=False,
        required=True,
    )