# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import models


class AbstractReport(models.AbstractModel):
    _inherit = "report.account_financial_report.abstract_report"

    def _get_move_lines_domain_not_reconciled(
        self, company_id, account_ids, partner_ids, only_posted_moves, date_from
    ):
        domain = super()._get_move_lines_domain_not_reconciled(
            company_id, account_ids, partner_ids, only_posted_moves, date_from
        )
        document_date_from = self.env.context.get("document_date_from")
        document_date_to = self.env.context.get("document_date_to")
        if document_date_from:
            domain = domain + [("invoice_date", ">=", document_date_from)]
        if document_date_to:
            domain = domain + [("invoice_date", "<=", document_date_to)]
        return domain
