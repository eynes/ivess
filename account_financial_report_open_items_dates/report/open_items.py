# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from datetime import datetime

from odoo import models


class OpenItemsReport(models.AbstractModel):
    _inherit = "report.account_financial_report.open_items"

    def _get_ml_fields(self):
        return super()._get_ml_fields() + ["invoice_date"]

    def _get_report_values(self, docids, data):
        document_date_from = data.get("document_date_from")
        document_date_to = data.get("document_date_to")
        res = super(
            OpenItemsReport,
            self.with_context(
                document_date_from=document_date_from,
                document_date_to=document_date_to,
            ),
        )._get_report_values(docids, data)
        res.update(
            {
                "document_date_from": document_date_from
                and datetime.strptime(document_date_from, "%Y-%m-%d").strftime(
                    "%d/%m/%Y"
                ),
                "document_date_to": document_date_to
                and datetime.strptime(document_date_to, "%Y-%m-%d").strftime(
                    "%d/%m/%Y"
                ),
            }
        )
        return res
