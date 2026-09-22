from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    other_payment_journal_id = fields.Many2one(
        related="company_id.other_payment_journal_id",
        string="Diario de Otros Pagos",
        domain="[('type', '=', 'payment'), ('company_id', '=', company_id)]",
        readonly=False,
    )
