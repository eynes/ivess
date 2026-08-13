from odoo import fields, models


class IvessInvoiceImportResultLine(models.TransientModel):
    _name = "ivess.invoice.import.result.line"
    _description = "Línea de factura agrupada (previsualización/resultado de importación)"
    _order = "id"

    wizard_id = fields.Many2one(
        "ivess.invoice.import.wizard",
        required=True,
        ondelete="cascade",
    )
    tipo_comprobante = fields.Char(string="Tipo comprobante")
    letra = fields.Char(string="Letra")
    pto_vta = fields.Char(string="Punto de venta")
    numero_comprobante = fields.Char(string="Número de comprobante")
    comprobante_ref = fields.Char(
        string="Referencia (aguas)",
        help="Clave compuesta letra+pto_vta+numero, tal como la usa el"
        " sistema origen. Se guarda en account.move.ref para deduplicar"
        " reimportaciones.",
    )
    comprobante_display = fields.Char(string="Comprobante", compute="_compute_comprobante_display")
    fecha = fields.Date(string="Fecha")
    fecha_vto = fields.Date(string="Fecha vto.")
    importe_total = fields.Float(string="Importe total")
    comprobante_anulado = fields.Boolean(string="Anulado en origen")
    estado_proyectado = fields.Selection(
        [
            ("draft", "A crear y Registrar"),
            ("cancel", "A crear y Cancelar"),
        ],
        string="Estado proyectado",
        compute="_compute_estado_proyectado",
    )
    cae = fields.Char(string="CAE")
    cliente_codigo = fields.Char(string="Código de cliente (origen)")
    cliente_razon_social = fields.Char(string="Razón social (origen)")
    cliente_documento = fields.Char(string="CUIT/documento (origen)")
    partner_id = fields.Many2one("res.partner", string="Cliente")
    voucher_type_id = fields.Many2one("res.voucher.type", string="Tipo de comprobante Odoo")
    detail_line_ids = fields.One2many(
        "ivess.invoice.import.detail.line",
        "result_line_id",
        string="Líneas de detalle",
    )
    detail_count = fields.Integer(string="Cant. líneas", compute="_compute_detail_count")
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Text(string="Detalle del error")
    resultado = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("ok", "OK"),
            ("error", "Error"),
        ],
        string="Resultado",
        default="pending",
    )
    odoo_move_id = fields.Many2one("account.move", string="Factura Odoo")

    def _compute_comprobante_display(self):
        for line in self:
            line.comprobante_display = "%s %s %s-%s" % (
                line.tipo_comprobante or "",
                line.letra or "",
                (line.pto_vta or "").zfill(4),
                (line.numero_comprobante or "").zfill(8),
            )

    def _compute_estado_proyectado(self):
        for line in self:
            line.estado_proyectado = "cancel" if line.comprobante_anulado else "draft"

    def _compute_detail_count(self):
        for line in self:
            line.detail_count = len(line.detail_line_ids)
