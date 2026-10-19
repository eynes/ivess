from odoo import models

from ..translation_repair import fix_text


class GeneralLedgerXlsx(models.AbstractModel):
    _inherit = "report.a_f_r.report_general_ledger_xlsx"

    def _get_report_columns(self, report):
        # Los encabezados salen del código de account_financial_report, cuya
        # traducción es_AR viene con la codificación rota ("D??bito").
        columns = super()._get_report_columns(report)
        for column in columns.values():
            column["header"] = fix_text(column["header"])
        return columns
