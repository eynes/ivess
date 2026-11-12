from odoo import _, fields, models
from odoo.exceptions import UserError


class IvessPaymentImportDetailLine(models.TransientModel):
    _name = "ivess.payment.import.detail.line"
    _description = (
        "Línea de aplicación a factura (previsualización) de importación de cobros"
    )

    result_line_id = fields.Many2one(
        "ivess.payment.import.result.line",
        required=True,
        ondelete="cascade",
    )
    tipo_compr_asoc = fields.Char(string="Tipo compr. asociado")
    letra_asoc = fields.Char(string="Letra")
    pto_venta_asoc = fields.Char(string="Punto de venta")
    numero_compr_asoc = fields.Char(string="Número")
    invoice_id = fields.Many2one(
        "account.move",
        string="Factura",
        domain="[('id', 'in', candidate_invoice_ids)]",
        help="Factura a la que se imputa. Si no se encontró, se puede elegir"
        " una de las candidatas antes de confirmar.",
    )
    candidate_invoice_ids = fields.Many2many(
        "account.move",
        "ivess_pay_import_detail_candidate_rel",
        "detail_id",
        "move_id",
        string="Facturas candidatas",
    )
    importe = fields.Float(string="Importe aplicado")
    payment_mode_id = fields.Many2one(
        "account.journal",
        string="Diario del medio de pago",
        help="Diario de caja/banco resuelto a partir de 'medio de pago' +"
        " 'caja' contra el mapeo configurable"
        " ivess.payment.import.payment.method.code.",
    )
    medio_pago = fields.Char(string="Medio de pago (origen)")
    moneda = fields.Char(string="Moneda (origen)")
    tipo_cambio = fields.Char(string="Tipo de cambio (origen)")
    caja = fields.Char(string="Caja (origen)")
    importe_movimiento = fields.Float(string="Importe del movimiento (origen)")
    cod_bco = fields.Char(string="Cód. banco (origen)")
    sucursal_bco = fields.Char(string="Sucursal banco (origen)")
    importe_movimiento_moneda_local = fields.Float(
        string="Importe del movimiento en moneda local (origen)"
    )
    is_check = fields.Boolean(string="Cheque")
    nro_cheque = fields.Char(string="Nº de cheque")
    check_type = fields.Selection(
        [("common", "Común"), ("deferred", "Diferido")], string="Tipo de cheque"
    )
    check_format = fields.Selection(
        [("physical", "Físico"), ("echeq", "Echeq")], string="Formato"
    )
    reception_date = fields.Date(string="Fecha de recepción")
    issue_date = fields.Date(string="Fecha de emisión")
    payment_date = fields.Date(string="Fecha de vencimiento")
    bank_id = fields.Many2one("res.bank", string="Banco del cheque")
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Char(string="Detalle del error")

    def write(self, vals):
        if "invoice_id" in vals:
            for detail in self:
                detail._check_chosen_invoice(vals["invoice_id"])
        res = super().write(vals)
        if "invoice_id" in vals:
            self._refresh_warning()
        return res

    def _check_chosen_invoice(self, invoice_id):
        if not invoice_id:
            return
        invoice = self.env["account.move"].browse(invoice_id)
        result = self.result_line_id
        if invoice.state != "posted" or invoice.move_type != "out_invoice":
            raise UserError(
                _("La factura '%s' no está confirmada.") % invoice.display_name
            )
        if result.partner_id and invoice.partner_id.commercial_partner_id != (
            result.partner_id.commercial_partner_id
        ):
            raise UserError(
                _("La factura '%(inv)s' es de otro cliente (%(p)s).")
                % {"inv": invoice.display_name, "p": invoice.partner_id.display_name}
            )
        total = sum(
            d.importe
            for d in result.detail_line_ids
            if d.invoice_id == invoice or d.id == self.id
        )
        if total - invoice.amount_residual > 0.01:
            raise UserError(
                _(
                    "El importe aplicado (%(a).2f) supera el saldo pendiente de"
                    " la factura '%(inv)s' (%(r).2f)."
                )
                % {
                    "a": total,
                    "inv": invoice.display_name,
                    "r": invoice.amount_residual,
                }
            )

    def _refresh_warning(self):
        """Quita de la advertencia del cobro la de los comprobantes que ya
        quedaron imputados a una factura."""
        for result in self.result_line_id:
            lines = (result.warning_message or "").split("\n")
            for detail in result.detail_line_ids.filtered("invoice_id"):
                key = "'%s%s%s'" % (
                    detail.letra_asoc or "",
                    (detail.pto_venta_asoc or "").zfill(4),
                    (detail.numero_compr_asoc or "").zfill(8),
                )
                lines = [ln for ln in lines if key not in ln]
            result.warning_message = "\n".join(lines) or False
