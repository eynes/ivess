from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    free_of_charge = fields.Boolean(string='Sin Cargo', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', readonly=True)

    def _select_additional_fields(self):
        result = super()._select_additional_fields()
        result['free_of_charge'] = 'l.free_of_charge'
        result['location_id'] = """(
            SELECT sp.location_id
            FROM stock_picking sp
            JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
            WHERE sp.sale_id = s.id
                AND spt.code = 'outgoing'
            ORDER BY sp.id
            LIMIT 1
        )"""
        return result

    def _group_by_sale(self):
        return super()._group_by_sale() + ', l.free_of_charge'
