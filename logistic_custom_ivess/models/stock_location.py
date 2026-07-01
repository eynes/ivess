from odoo import models, fields


class StockLocation(models.Model):
    _inherit = 'stock.location'

    template_delivery_route_ids = fields.Many2many(
        'template.delivery.route',
        'template_delivery_route_stock_location_rel',
        'location_id',
        'route_id',
        string='Distribuciones',
    )
