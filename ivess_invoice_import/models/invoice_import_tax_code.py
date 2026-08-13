from odoo import fields, models


class IvessInvoiceImportTaxCode(models.Model):
    _name = "ivess.invoice.import.tax.code"
    _description = "Mapeo de código de impuesto especial (Excel 'aguas') a impuesto Odoo"
    _rec_name = "code"

    code = fields.Char(
        string="Código (origen)",
        required=True,
        help="Valor tal como viene en la columna 'cod impuesto especial' del"
        " Excel de importación de facturas/cobros.",
    )
    tax_id = fields.Many2one(
        "account.tax",
        string="Impuesto Odoo",
        required=True,
        domain=[("tax_group_id.group_type", "in", ("perception", "internals"))],
        help="Percepción (IIBB, IVA, etc.) o impuesto interno de Odoo al que"
        " corresponde este código. Según el tipo del impuesto elegido, el"
        " importador crea una línea en account.move.perception_ids o en"
        " account.move.internal_taxes_ids.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Ya existe un mapeo para ese código en esta compañía.",
        ),
    ]
