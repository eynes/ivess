from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def default_get(self, fields):
        result = super().default_get(fields)
        is_other_payment = self.env.context.get("default_other_payment", False)
        default_type = self.env.context.get("default_type", False)
        if "journal_id" in fields and is_other_payment and default_type == "payment":
            company_journal = self.env.company.other_payment_journal_id
            if company_journal:
                result["journal_id"] = company_journal.id
        return result
