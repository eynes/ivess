from odoo import fields, models


class PerceptionTaxLine(models.Model):
    _inherit = 'perception.tax.line'

    invoice_date = fields.Date(
        related='invoice_id.invoice_date',
        string='Fecha de Factura',
        store=True,
    )
