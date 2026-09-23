from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    ivess_force_manual_document_number = fields.Boolean(
        related="journal_id.ivess_force_manual_document_number",
    )

    def _required_internal_number(self):
        """Customer invoices on a journal with manual numbering forced must
        have an internal_number set to be posted."""
        for record in self:
            if (
                record.is_sale_document()
                and record.journal_id.ivess_force_manual_document_number
                and not record.internal_number
            ):
                raise ValidationError(_("You must complete the invoice number."))

    def _post(self, soft=True):
        self._required_internal_number()
        return super()._post(soft=soft)
