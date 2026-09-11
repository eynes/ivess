from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _report_xls_query_extra(self):
        select_extra, join_extra, where_extra, sort_selection = (
            super()._report_xls_query_extra()
        )
        where_extra += " AND pa.fiscal_type != 'internal_voucher' "
        return (select_extra, join_extra, where_extra, sort_selection)
