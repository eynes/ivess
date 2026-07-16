from odoo import models, fields, api


class StockLocation(models.Model):
    _inherit = 'stock.location'

    delivery_route_number_id = fields.Many2one(
        'delivery.route.number',
        string='Reparto',
        compute='_compute_delivery_route_number_id',
    )

    @api.depends()
    def _compute_delivery_route_number_id(self):
        for rec in self:
            rec.delivery_route_number_id = self.env['delivery.route.number'].search(
                [('location_id', '=', rec.id)], limit=1
            )
