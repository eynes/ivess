from odoo import models, fields, api


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    internal_notes = fields.Text(string="Internal notes")
