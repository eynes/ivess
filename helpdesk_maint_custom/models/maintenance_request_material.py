# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models


class MaintenanceRequestMaterial(models.Model):
    _name = 'maintenance.request.material'
    _description = 'Maintenance Request Material'

    request_id = fields.Many2one(
        'maintenance.request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('type', 'in', ['consu', 'product'])]",
    )
    description = fields.Char(string='Description', compute='_compute_description', store=True, readonly=False)
    product_uom_qty = fields.Float(string='Demand', default=1.0, digits='Product Unit of Measure')
    quantity = fields.Float(string='Quantity', digits='Product Unit of Measure')
    product_uom = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        compute='_compute_product_uom',
        store=True,
        readonly=False,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        groups='stock.group_production_lot',
        domain="[('product_id', '=', product_id)]",
    )
    company_id = fields.Many2one(related='request_id.company_id', store=True)

    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            line.description = line.product_id.name or ''

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if not line.product_uom:
                line.product_uom = line.product_id.uom_id
