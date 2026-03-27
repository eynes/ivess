from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allow_free_of_charge = fields.Boolean(string='Allow Free Of Charge')
    liter_quantity = fields.Float(string='Liter Quantity', help='Liters per unit of this product')
