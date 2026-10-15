from odoo import fields, models


class IvessPaymentImportRetentionCode(models.Model):
    _name = "ivess.payment.import.retention.code"
    _description = "Mapeo de código de retención (Excel 'aguas', cobros) a impuesto Odoo"
    _rec_name = "code"

    code = fields.Char(
        string="Código (origen)",
        required=True,
        help="Valor tal como viene en las columnas 'retencion 1..5' del Excel"
        " de importación de cobros.",
    )
    tax_id = fields.Many2one(
        "account.tax",
        string="Retención Odoo",
        required=True,
        domain=[
            ("tax_group_id.group_type", "=", "retention"),
            ("type_tax_use", "=", "sale"),
        ],
        help="Impuesto de retención de ventas de Odoo al que corresponde este"
        " código. El importador crea una línea de retención"
        " (account.payment.order.retention.line) en el recibo con el monto"
        " de la columna 'monto retencion N' correspondiente.",
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
            "Ya existe un mapeo para ese código de retención en esta compañía.",
        ),
    ]
