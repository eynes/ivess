from odoo import fields, models


class CreateCheckbookWizard(models.TransientModel):
    _inherit = "create.checkbook.wizard"

    crossed_by_default = fields.Boolean(string="Crossed by Default")

    def create_checkbook(self):
        result = super().create_checkbook()
        if self.crossed_by_default:
            payment_method = self.env.ref("l10n_ar_eynes.account_payment_method_check")
            checkbook_line = self.env["account.payment.method.line"].search(
                [
                    ("journal_id", "=", self.journal_id.id),
                    ("payment_method_id", "=", payment_method.id),
                    ("format", "=", self.checkbook_format),
                    ("number", "=", int(self.number)),
                ],
                limit=1,
            )
            if checkbook_line:
                checkbook_line.crossed_by_default = True
        return result
