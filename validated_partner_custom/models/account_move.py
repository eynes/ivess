from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMove(models.Model):

    _inherit = "account.move"

    def _post(self, soft=True):
        for move in self:
            if move.move_type == 'in_invoice':
                move._validate_purchase_invoice(move)
        return super()._post(soft=soft)

    def _validate_purchase_invoice(self, move):
        if not move.partner_id.validated_supplier:
            raise UserError(
                _(
                    "The selected supplier '%s' is not validated by the Administration team. "
                    "Please request validation."
                ) % move.partner_id.display_name
            )
