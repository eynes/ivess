from odoo import fields, models


class IvessPaymentImportDetailLine(models.TransientModel):
    _name = "ivess.payment.import.detail.line"
    _description = "Línea de aplicación a factura (previsualización) de importación de cobros"

    result_line_id = fields.Many2one(
        "ivess.payment.import.result.line",
        required=True,
        ondelete="cascade",
    )
    tipo_compr_asoc = fields.Char(string="Tipo compr. asociado")
    letra_asoc = fields.Char(string="Letra")
    pto_venta_asoc = fields.Char(string="Punto de venta")
    numero_compr_asoc = fields.Char(string="Número")
    invoice_id = fields.Many2one("account.move", string="Factura")
    importe = fields.Float(string="Importe aplicado")
    medio_pago = fields.Char(
        string="Medio de pago (origen)",
        help="Informativo: no determina el diario/método de pago usado en Odoo.",
    )
    moneda = fields.Char(string="Moneda (origen)")
    tipo_cambio = fields.Char(string="Tipo de cambio (origen)")
    caja = fields.Char(
        string="Caja (origen)",
        help="Informativo: no determina el diario usado en Odoo.",
    )
    importe_movimiento = fields.Float(string="Importe del movimiento (origen)")
    cod_bco = fields.Char(string="Cód. banco (origen)")
    sucursal_bco = fields.Char(string="Sucursal banco (origen)")
    importe_movimiento_moneda_local = fields.Float(
        string="Importe del movimiento en moneda local (origen)"
    )
    has_error = fields.Boolean(string="Con error")
    error_message = fields.Char(string="Detalle del error")
