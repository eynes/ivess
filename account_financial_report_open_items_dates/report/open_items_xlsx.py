# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

from odoo import models


class OpenItemsXslx(models.AbstractModel):
    _inherit = "report.a_f_r.report_open_items_xlsx"

    def _get_report_columns(self, report):
        res = super()._get_report_columns(report)
        res[0]["header"] = self.env._("Accounting Date")
        new_res = {0: res[0]}
        new_res[1] = {
            "header": self.env._("Document Date"),
            "field": "invoice_date",
            "width": 11,
        }
        for col_pos in sorted(key for key in res if key != 0):
            new_res[col_pos + 1] = res[col_pos]
        return new_res

    def _get_report_filters(self, report):
        res = super()._get_report_filters(report)
        if report.document_date_from or report.document_date_to:
            res.append(
                [
                    self.env._("Document date filter"),
                    "%s - %s"
                    % (
                        report.document_date_from.strftime("%d/%m/%Y")
                        if report.document_date_from
                        else "",
                        report.document_date_to.strftime("%d/%m/%Y")
                        if report.document_date_to
                        else "",
                    ),
                ]
            )
        return res
