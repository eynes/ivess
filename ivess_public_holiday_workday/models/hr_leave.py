from odoo import models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _get_domain_from_get_unusual_days(self, date_from, date_to=None):
        domain = super()._get_domain_from_get_unusual_days(
            date_from=date_from, date_to=date_to
        )
        domain.append(("is_workday", "=", False))
        return domain
