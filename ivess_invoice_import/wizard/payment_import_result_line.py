from odoo import fields, models


class IvessPaymentImportResultLine(models.TransientModel):
    _name = "ivess.payment.import.result.line"
    _description = (
        "Línea de recibo de cobro agrupada (previsualización/resultado de importación)"
    )
    _order = "id"

    wizard_id = fields.Many2one(
        "ivess.payment.import.wizard",
        required=True,
        ondelete="cascade",
    )
    tipo_comprobante = fields.Char(string="Tipo comprobante")
    letra = fields.Char(string="Letra")
    pto_vta = fields.Char(string="Punto de venta")
    numero_comprobante = fields.Char(string="Número de comprobante")
    comprobante_ref = fields.Char(
        string="Referencia (aguas)",
        help="Clave compuesta letra+pto_vta+numero del recibo, tal como la"
        " usa el sistema origen. Se guarda en account.payment.order.reference"
        " para deduplicar reimportaciones.",
    )
    comprobante_display = fields.Char(
        string="Comprobante", compute="_compute_comprobante_display"
    )
    fecha = fields.Date(string="Fecha")
    importe_total = fields.Float(string="Importe total")
    comprobante_anulado = fields.Boolean(string="Anulado en origen")
    estado_proyectado = fields.Selection(
        [
            ("create", "A crear"),
            ("skip", "Anulado en origen: no se importa"),
        ],
        string="Estado proyectado",
        compute="_compute_estado_proyectado",
    )
    cliente_codigo = fields.Char(string="Código de cliente (origen)")
    partner_id = fields.Many2one("res.partner", string="Cliente")
    journal_id = fields.Many2one(
        "account.journal",
        string="Diario",
        help="Diario de Recibo de Cobranza (type='receipt') resuelto"
        " automáticamente: el único diario de ese tipo de la compañía.",
    )
    detail_line_ids = fields.One2many(
        "ivess.payment.import.detail.line",
        "result_line_id",
        string="Facturas aplicadas",
    )
    detail_count = fields.Integer(
        string="Cant. facturas", compute="_compute_detail_count"
    )
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Text(string="Detalle del error")
    resultado = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("ok", "OK"),
            ("error", "Error"),
            ("skipped", "Anulado (no importado)"),
        ],
        string="Resultado",
        default="pending",
    )
    odoo_payment_order_id = fields.Many2one(
        "account.payment.order", string="Recibo de cobranza Odoo"
    )

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
            line.estado_proyectado = "skip" if line.comprobante_anulado else "create"

    def _compute_detail_count(self):
        for line in self:
            line.detail_count = len(line.detail_line_ids)
