# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import fields, models


class OpenItemsReportWizard(models.TransientModel):
    _inherit = "open.items.report.wizard"

    document_date_from = fields.Date(
        string="Document Date from",
        help="Filter open items by document date (invoice date). "
        "Only relevant for invoices (e.g. vendor bills), where the "
        "document date can differ from the accounting date.",
    )
    document_date_to = fields.Date(
        string="Document Date to",
        help="Filter open items by document date (invoice date). "
        "Only relevant for invoices (e.g. vendor bills), where the "
        "document date can differ from the accounting date.",
    )

    def _prepare_report_open_items(self):
        res = super()._prepare_report_open_items()
        res.update(
            {
                "document_date_from": self.document_date_from
                and fields.Date.to_string(self.document_date_from),
                "document_date_to": self.document_date_to
                and fields.Date.to_string(self.document_date_to),
            }
        )
        return res
