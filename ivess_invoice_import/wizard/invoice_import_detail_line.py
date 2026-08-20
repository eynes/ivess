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
    special_tax_ids = fields.One2many(
        "ivess.invoice.import.detail.special.tax",
        "detail_line_id",
        string="Impuestos especiales/internos",
        help="Impuestos especiales o internos detectados en esta línea (columnas"
        " 'cod impuesto interno', 'cod imp especiales', 'cod imp especiales1' y"
        " 'cod imp especiales2' del Excel). Cada uno se agrega tal cual (base y"
        " monto del Excel, sin recalcular) como percepción o impuesto interno"
        " de la factura.",
    )
    special_tax_display = fields.Char(
        string="Impuestos especiales/internos",
        compute="_compute_special_tax_display",
        help="Resumen de special_tax_ids para mostrar en la lista.",
    )
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Char(string="Detalle del error")

    def _compute_special_tax_display(self):
        for line in self:
            line.special_tax_display = ", ".join(
                "%s: %.2f" % (special.tax_id.name, special.monto)
                for special in line.special_tax_ids
            )
