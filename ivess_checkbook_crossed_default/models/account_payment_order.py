from odoo import api, models


class AccountPaymentOrderIssuedCheckLine(models.Model):
    _inherit = "account.payment.order.issued.check.line"

    @api.onchange("checkbook_id", "issued_check_id")
    def _onchange_checkbook_id_crossed_by_default(self):
        if self.issued_check_id:
            self.crossed = self.issued_check_id.crossed
        elif self.checkbook_id:
            self.crossed = self.checkbook_id.crossed_by_default
