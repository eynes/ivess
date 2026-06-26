from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allow_free_of_charge = fields.Boolean(string='Allow Free Of Charge')
    liter_quantity = fields.Float(string='Liter Quantity', help='Liters per unit of this product')
    container_type = fields.Selection(
        [
            ('bottle', 'Botella'),
            ('jug', 'Bidón'),
        ],
        string='Tipo de Envase',
    )
    monthly_limit_free_of_charge = fields.Integer(string='Monthly Free Of Charge Limit', help='Maximum quantity allowed for free of charge per month')
