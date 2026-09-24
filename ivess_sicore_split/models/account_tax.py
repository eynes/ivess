from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    sicore_tax_code = fields.Char(
        string='SICORE Tax Code',
        size=4,
        help="Código de impuesto SICORE (codigo_impuesto) a informar para "
        "esta percepción. Si no se completa, se sigue buscando en el "
        "diario vinculado a este impuesto (Accounting->Configuration->"
        "Journals->AFIP Code).",
    )
