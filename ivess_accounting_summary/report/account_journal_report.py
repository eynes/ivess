from odoo import _, models


class AccountJournalReportHandler(models.AbstractModel):
    _inherit = "account.journal.report.handler"

    def _get_export_lines_for_journal(
        self, report, options, export_type, journal_vals, account_move_vals_list
    ):
        # Solo colapsamos en la impresión PDF (Libro Diario). La exportación
        # XLSX y la navegación en pantalla conservan el detalle completo,
        # necesario para auditoría y conciliación.
        if export_type == "pdf" and journal_vals.get("type") != "bank":
            account_move_vals_list = self._ivess_collapse_summarized_accounts(
                account_move_vals_list
            )
        return super()._get_export_lines_for_journal(
            report, options, export_type, journal_vals, account_move_vals_list
        )

    def _ivess_collapse_summarized_accounts(self, account_move_vals_list):
        """Colapsa, por asiento, las líneas de cuentas x_summarize_on_report.

        Cada asiento resumen mensual (Diario de Refundición) trae una línea
        de deuda legal por cada partner/comprobante original, para poder
        conciliar cobranzas contra cada una (ver x_origin_document_id). Al
        imprimir el libro legal, esas líneas deben verse como un único
        monto totalizador con la leyenda "(Resumen Global)", sin exponer el
        desglose por partner.
        """
        summarized_codes = set(
            self.env["account.account"]
            .search([("x_summarize_on_report", "=", True)])
            .mapped("code")
        )
        if not summarized_codes:
            return account_move_vals_list

        collapsed_list = []
        for move_line_entries in account_move_vals_list:
            grouped_by_code = {}
            collapsed_entries = []
            for entry in move_line_entries:
                code = entry.get("account_code")
                if code not in summarized_codes:
                    collapsed_entries.append(entry)
                    continue
                merged_entry = grouped_by_code.get(code)
                if merged_entry is None:
                    merged_entry = dict(entry)
                    merged_entry.update(
                        {
                            "partner_name": _("(Resumen Global)"),
                            "name": "",
                            "reference": "",
                            "debit": 0.0,
                            "credit": 0.0,
                            "balance": 0.0,
                        }
                    )
                    grouped_by_code[code] = merged_entry
                    collapsed_entries.append(merged_entry)
                merged_entry["debit"] += entry["debit"]
                merged_entry["credit"] += entry["credit"]
                merged_entry["balance"] += entry["balance"]
            collapsed_list.append(collapsed_entries)
        return collapsed_list
