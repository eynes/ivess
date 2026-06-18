from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    delivery_route_ids = fields.Many2many(
        comodel_name='delivery.route',
        string='Reparto',
        compute='_compute_delivery_route_ids',
        store=True,
        readonly=True,
        tracking=True
    )
    
    @api.depends(
        'invoice_origin', 
        'move_type', 
        'associated_inv_ids.invoice_origin'
    )
    def _compute_delivery_route_ids(self):
        for move in self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund', 'out_receipt')):
            routes = self.env['delivery.route']
            SaleOrderObj = self.env['sale.order']
            # Desde el invoice_origin de esta factura
            origin_names = [name.strip() for name in (move.invoice_origin or '').split(',') if name.strip()]
            sale_orders = SaleOrderObj.search([
                ('name', 'in', origin_names)
            ])
            routes |= sale_orders.mapped('delivery_route_id')

            # Desde las facturas asociadas
            for associated_inv in move.associated_inv_ids:
                associated_origins = [name.strip() for name in (associated_inv.invoice_origin or '').split(',') if name.strip()]
                associated_orders = SaleOrderObj.search([
                    ('name', 'in', associated_origins)
                ])
                routes |= associated_orders.mapped('delivery_route_id')

            move.delivery_route_ids = routes