from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    other_payment_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de Otros Pagos",
        domain="[('type', '=', 'payment'), ('company_id', '=', id)]",
        help=(
            "Diario propuesto por defecto al crear un registro desde el "
            "menú Otros Pagos."
        ),
    )
