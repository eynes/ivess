from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends(
        'move_id.show_fiscal_credit',
        'move_id.move_type',
        'tax_ids',
    )
    def _compute_required_fiscal_credit(self):
        for move_line in self:
            move = move_line.move_id
            required = False
            if move.show_fiscal_credit and move.move_type in (
                'in_invoice',
                'in_refund',
            ):
                vat_taxes = move_line.tax_ids.filtered(
                    lambda tax: tax.tax_group_id.group_type == 'vat'
                )
                zero_percent_purchase_vat = vat_taxes.filtered(
                    lambda tax: tax.type_tax_use == 'purchase'
                    and not tax.is_exempt
                    and tax.amount == 0
                )
                required = bool(vat_taxes - zero_percent_purchase_vat)
            move_line.required_fiscal_credit = required
