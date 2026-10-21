from odoo import models


class AccountTaxSubjournalApportionableWizard(models.TransientModel):
    _inherit = 'account.tax.subjournal.apportionable.wizard'

    def _get_line_vals(self):
        """Internal vouchers must not appear in the apportionable VAT
        subjournal."""
        rows = super()._get_line_vals()
        if not rows:
            return rows
        move_ids = {row['invoice_id'] for row in rows}
        internal_ids = set(
            self.env['account.move']
            .browse(move_ids)
            .filtered(lambda m: m.journal_id.fiscal_type == 'internal_voucher')
            .ids
        )
        return [row for row in rows if row['invoice_id'] not in internal_ids]
