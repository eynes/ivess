from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    require_cae_vendor_bill = fields.Boolean(
        string="Exigir CAE en facturas de proveedor",
        default=False,
        help=(
            "Si está tildado, el CAE y su fecha de vencimiento son "
            "obligatorios para validar facturas y notas de crédito "
            "de proveedor de esta compañía."
        ),
    )
