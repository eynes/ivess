from odoo import api, models


class AccountCheck(models.Model):
    _inherit = "account.check"

    @api.model_create_multi
    def create(self, vals_list):
        for val in vals_list:
            if val.get("checkbook_id") and "crossed" not in val:
                checkbook = self.env["account.payment.method.line"].browse(
                    val["checkbook_id"]
                )
                if checkbook.crossed_by_default:
                    val["crossed"] = True
        return super().create(vals_list)
