from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    crossed_by_default = fields.Boolean(string="Crossed by Default")

    def write(self, vals):
        res = super().write(vals)
        if "crossed_by_default" in vals:
            checks = self.env["account.check"].search(
                [("checkbook_id", "in", self.ids)]
            )
            if checks:
                checks.write({"crossed": bool(vals["crossed_by_default"])})
        return res
