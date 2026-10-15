from odoo import fields, models


class IvessPaymentImportRetentionLine(models.TransientModel):
    _name = "ivess.payment.import.retention.line"
    _description = "Retención de un recibo (previsualización) de importación de cobros"

    result_line_id = fields.Many2one(
        "ivess.payment.import.result.line",
        required=True,
        ondelete="cascade",
    )
    codigo = fields.Char(string="Código (origen)")
    tax_id = fields.Many2one("account.tax", string="Retención Odoo")
    importe = fields.Float(string="Monto")
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Char(string="Detalle del error")
