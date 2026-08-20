from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    bejerman_code = fields.Char(
        string="Código Bejerman",
        help="Código con el que esta percepción está identificada en el"
        " sistema Bejerman del cliente. Se usa para matchear la columna"
        " 'cod impuesto especial' del Excel de importación de facturas con"
        " la percepción correspondiente.",
    )

    _sql_constraints = [
        (
            "bejerman_code_company_uniq",
            "unique(bejerman_code, company_id)",
            "Ya existe un impuesto con ese código Bejerman en esta compañía.",
        ),
    ]
