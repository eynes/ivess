from odoo import fields, models


class IvessInvoiceImportDetailLine(models.TransientModel):
    _name = "ivess.invoice.import.detail.line"
    _description = "Línea de detalle (previsualización) de importación de facturas"

    result_line_id = fields.Many2one(
        "ivess.invoice.import.result.line",
        required=True,
        ondelete="cascade",
    )
    tipo_item = fields.Char(string="Tipo de ítem")
    cod_art = fields.Char(string="Código de artículo (cliente)")
    product_id = fields.Many2one("product.product", string="Producto")
    cantidad = fields.Float(string="Cantidad")
    precio_unitario = fields.Float(string="Precio unitario")
    tasa_iva = fields.Float(string="Tasa de IVA (%)")
    tax_id = fields.Many2one("account.tax", string="Impuesto")
    importe_total_neto_item = fields.Float(string="Importe total neto del ítem")
    importe_del_renglon = fields.Char(
        string="Importe del renglón (origen)",
        help="Valor tal como vino en el archivo. Es solo informativo: no se"
        " usa para calcular la factura en Odoo (se recalcula a partir de"
        " cantidad x precio unitario x impuesto).",
    )
    cod_impuesto_especial = fields.Char(string="Código impuesto especial")
    monto_imp = fields.Float(
        string="Monto impuesto especial",
        help="Informativo: este importe no se aplica a la factura, esta"
        " versión del importador no soporta impuestos especiales.",
    )
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Char(string="Detalle del error")
