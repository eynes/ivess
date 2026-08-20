# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import api, fields, models


class OpenItemsReportWizard(models.TransientModel):
    _inherit = "open.items.report.wizard"

    filter_by_document_date = fields.Boolean(
        string="Filter by document date",
        default=False,
        help="If disabled, open items are filtered only by the accounting "
        "date (native behavior). If enabled, open items are also filtered "
        "by their document date (invoice date) using the range below.",
    )
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

    @api.onchange("filter_by_document_date")
    def _onchange_filter_by_document_date(self):
        """Keep the two date-filter modes mutually exclusive.

        ``date_at`` stays required by the base report (it drives the
        "as of" balance calculation), so when it is hidden it must keep
        a valid value instead of being left blank.
        """
        if self.filter_by_document_date:
            self.date_from = False
            self.date_at = self.date_at or fields.Date.context_today(self)
        else:
            self.document_date_from = False
            self.document_date_to = False

    def _prepare_report_open_items(self):
        res = super()._prepare_report_open_items()
        document_date_from = self.filter_by_document_date and self.document_date_from
        document_date_to = self.filter_by_document_date and self.document_date_to
        res.update(
            {
                "document_date_from": document_date_from
                and fields.Date.to_string(document_date_from),
                "document_date_to": document_date_to
                and fields.Date.to_string(document_date_to),
            }
        )
        return res
