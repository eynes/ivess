from odoo import api, fields, models


class IvessPaymentImportPaymentMethodCode(models.Model):
    _name = "ivess.payment.import.payment.method.code"
    _description = (
        "Mapeo de medio de pago + caja/cód. banco (Excel 'aguas', cobros) a diario Odoo"
    )
    _rec_name = "medio_pago"

    medio_pago = fields.Selection(
        [
            ("1", "1 - Caja"),
            ("4", "4 - Cuenta bancaria"),
        ],
        string="Medio de pago (origen)",
        required=True,
        help="Código tal como viene en la columna 'medio de pago' del Excel"
        " de importación de cobros.",
    )
    caja = fields.Char(
        string="Caja (origen)",
        default="",
        help="Valor tal como viene en la columna 'caja' del Excel de"
        " importación de cobros. Se usa para desambiguar medios de pago en"
        " efectivo (ej. varias cajas físicas). Dejar vacío si no aplica.",
    )
    cod_bco = fields.Char(
        string="Cód. banco (origen)",
        default="",
        help="Valor tal como viene en la columna 'cod bco' del Excel de"
        " importación de cobros. Se usa para desambiguar medios de pago"
        " bancarios cuando hay más de una cuenta bancaria posible bajo el"
        " mismo medio de pago (ej. HSBC vs Mercado Pago). Se autocompleta"
        " al elegir el diario (a partir del BIC de su cuenta bancaria),"
        " pero se puede pisar a mano. Dejar vacío si no aplica.",
    )
    sucursal_bco = fields.Char(
        string="Sucursal banco (origen)",
        default="",
        help="Valor tal como viene en la columna 'sucursal del bco' del"
        " Excel de importación de cobros. Se autocompleta al elegir el"
        " diario (con el número de cuenta de su cuenta bancaria), pero se"
        " puede pisar a mano. Dejar vacío si no aplica.",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Diario Odoo",
        required=True,
        domain=[("type", "in", ("cash", "bank"))],
        help="Diario de caja/banco al que corresponde esta combinación de"
        " medio de pago + caja + cod. banco + sucursal. El importador de"
        " cobros arma una línea de payment_mode_line_ids por cada diario"
        " distinto resuelto dentro de un mismo recibo.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "medio_pago_caja_cod_bco_company_uniq",
            "unique(medio_pago, caja, cod_bco, sucursal_bco, company_id)",
            "Ya existe un mapeo para esa combinación de medio de pago +"
            " caja + cód. banco + sucursal en esta compañía.",
        ),
    ]

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        bank_account = self.journal_id.bank_account_id
        if bank_account.bank_id.bic:
            self.cod_bco = bank_account.bank_id.bic
        if bank_account.acc_number:
            self.sucursal_bco = bank_account.acc_number
