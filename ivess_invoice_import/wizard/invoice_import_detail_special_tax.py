from odoo import fields, models


class IvessInvoiceImportDetailSpecialTax(models.TransientModel):
    _name = "ivess.invoice.import.detail.special.tax"
    _description = (
        "Impuesto especial/interno detectado en una línea de detalle"
        " (previsualización de importación de facturas)"
    )

    detail_line_id = fields.Many2one(
        "ivess.invoice.import.detail.line",
        required=True,
        ondelete="cascade",
    )
    cod = fields.Char(string="Código (origen)")
    tax_id = fields.Many2one(
        "account.tax",
        string="Impuesto (mapeado)",
        help="Impuesto Odoo resuelto a partir del código de origen, según el"
        " mapeo configurado en Contabilidad > Configuración > Códigos de"
        " impuesto especial (importación).",
    )
    base = fields.Float(string="Base imponible")
    monto = fields.Float(string="Monto")
