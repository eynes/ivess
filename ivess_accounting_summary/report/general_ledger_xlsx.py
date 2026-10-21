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

    def _get_report_filters(self, report):
        # Mismo problema en los rótulos de filtros ("Filtro periodo").
        return [
            [fix_text(label), fix_text(value) if isinstance(value, str) else value]
            for label, value in super()._get_report_filters(report)
        ]
