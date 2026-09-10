from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    required_cae = fields.Boolean(
        compute="_compute_required_cae",
        store=False,
    )

    @api.depends("move_type", "company_id.require_cae_vendor_bill")
    def _compute_required_cae(self):
        for move in self:
            move.required_cae = (
                move.move_type in ("in_invoice", "in_refund")
                and move.company_id.require_cae_vendor_bill
            )
