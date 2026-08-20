from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountPaymentOrderIssuedCheckLine(models.Model):
    _inherit = 'account.payment.order.issued.check.line'

    @api.onchange('checkbook_id')
    def _onchange_checkbook_id(self):
        super()._onchange_checkbook_id()
        if not self.checkbook_id: # or self.echeq_without_number
            return
        self.issued_check_id = self._get_next_available_check()

    def _get_next_available_check(self):
        """Lowest free draft check number of the selected checkbook.

        Excludes checks already picked by sibling lines of the same
        payment order that are not saved yet: those still look "draft"
        in the database (their payment_order_id write only happens on
        create/write of this line), so without this exclusion two new
        lines added before saving the order could both suggest the same
        number.
        """
        self.ensure_one()
        taken_ids = (
            self.payment_order_id.issued_check_line_ids.filtered(
                lambda line: line != self and line.issued_check_id
            )
            .mapped('issued_check_id')
            .ids
        )
        return self.env['account.check'].search(
            [
                ('checkbook_id', '=', self.checkbook_id.id),
                ('internal_type', '=', 'issued'),
                ('issued_check_state', '=', 'draft'),
                ('payment_order_id', '=', False),
                ('id', 'not in', taken_ids),
            ],
            order='number asc',
            limit=1,
        )

    @api.constrains('issued_check_id')
    def _check_issued_check_id_unique_per_order(self):
        for line in self:
            if not line.issued_check_id or not line.payment_order_id:
                continue
            duplicate = line.payment_order_id.issued_check_line_ids.filtered(
                lambda other: other != line
                and other.issued_check_id == line.issued_check_id
            )
            if duplicate:
                raise ValidationError(
                    _("Check %s is already used in another line of this payment order.")
                    % line.issued_check_id.number
                )
