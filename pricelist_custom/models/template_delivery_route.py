from odoo import fields, models


class TemplateDeliveryRoute(models.Model):
    _inherit = 'template.delivery.route'

    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Lista de Precio",
        check_company=True,
    )
