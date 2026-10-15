from odoo import _, models


class JournalLedgerXlsx(models.AbstractModel):
    _inherit = "report.a_f_r.report_journal_ledger_xlsx"

    def _get_report_name(self, report, data=False):
        return _("Diario General")

    def _get_report_filters(self, report):
        # Los filtros se reemplazan por el encabezado del libro diario
        # (ver _write_report_title).
        return []

    def _write_report_title(self, title, report_data):
        report = self.env["journal.ledger.report.wizard"].browse(
            report_data["wizard_id"]
        )
        sheet = report_data["sheet"]
        last_col = len(report_data["columns"]) - 1
        lines = [
            _("DIARIO GENERAL"),
            report.company_id.name,
            _("EJERCICIO: %s", report._ivess_get_fiscal_year_name()),
            _("PERIODO: %s", report._ivess_get_period_text()),
        ]
        for line in lines:
            sheet.merge_range(
                report_data["row_pos"],
                0,
                report_data["row_pos"],
                last_col,
                line,
                report_data["formats"]["format_bold"],
            )
            report_data["row_pos"] += 1
        report_data["row_pos"] += 1

    def _define_formats(self, workbook, report_data, data=None):
        res = super()._define_formats(workbook, report_data, data=data)
        # _write_report_title solo recibe el título; el encabezado del libro
        # diario necesita el wizard.
        report_data["wizard_id"] = data["wizard_id"]
        return res

    def _get_report_columns(self, report):
        # "Débito"/"Crédito" van literales: la traducción es_AR de
        # account_financial_report viene con la codificación rota ("D??bito").
        columns = [
            {"header": _("Entry"), "field": "entry", "width": 18},
            {"header": _("Date"), "field": "date", "width": 11},
            {"header": _("Account"), "field": "account_code", "width": 9},
        ]
        if report.with_auto_sequence:
            columns.insert(
                0, {"header": _("Sequence"), "field": "auto_sequence", "width": 10}
            )
        if report.with_account_name:
            columns.append(
                {"header": _("Account Name"), "field": "account_name", "width": 30}
            )
        if not report.hide_partner:
            columns.append({"header": _("Partner"), "field": "partner", "width": 25})
        columns += [
            {"header": _("Ref - Label"), "field": "label", "width": 40},
            {"header": "Débito", "field": "debit", "type": "amount", "width": 14},
            {"header": "Crédito", "field": "credit", "type": "amount", "width": 14},
            {"header": _("Total"), "field": "total", "type": "amount", "width": 14},
        ]
        if report.foreign_currency:
            columns += [
                {
                    "header": _("Currency"),
                    "field": "currency_name",
                    "width": 14,
                    "type": "currency_name",
                },
                {
                    "header": _("Amount Currency"),
                    "field": "amount_currency",
                    "type": "amount",
                    "width": 18,
                },
            ]
        return dict(enumerate(columns))

    def _generate_report_content(self, workbook, report, data, report_data):
        res_data = self.env[
            "report.account_financial_report.journal_ledger"
        ]._get_report_values(report, data)
        report_data["workbook"] = workbook
        self.write_array_header(report_data)
        account_ids_data = res_data["account_ids_data"]
        partner_ids_data = res_data["partner_ids_data"]
        currency_ids_data = res_data["currency_ids_data"]
        move_ids_data = res_data["move_ids_data"]
        # Todo en una única hoja: los asientos de todos los diarios, en el
        # orden elegido en el wizard, sin hojas de resumen de impuestos.
        for move in self._ivess_get_ordered_moves(report, res_data):
            for line in move["report_move_lines"]:
                currency_data = currency_ids_data.get(line["currency_id"], False)
                account_data = account_ids_data.get(line["account_id"], False)
                move_data = move_ids_data.get(line["move_id"], False)
                line["partner"] = self._get_partner_name(
                    line["partner_id"], partner_ids_data
                )
                line["account_code"] = account_data and account_data["code"] or ""
                line["account_name"] = account_data and account_data["name"] or ""
                line["currency_name"] = currency_data and currency_data["name"] or ""
                line["entry"] = move_data and move_data["entry"] or ""
                self.write_line_from_dict(line, report_data)
            report_data["row_pos"] += 1
        self._ivess_write_grand_total(report_data, res_data["grand_total"])

    def _ivess_get_ordered_moves(self, report, res_data):
        if report.group_option == "journal":
            return [
                move
                for ledger in res_data["Journal_Ledgers"]
                for move in ledger["report_moves"]
            ]
        return res_data["Moves"]

    def _ivess_write_grand_total(self, report_data, grand_total):
        sheet = report_data["sheet"]
        formats = report_data["formats"]
        row = report_data["row_pos"]
        label_col = None
        for col_pos, column in report_data["columns"].items():
            if column["field"] == "label":
                label_col = col_pos
            if column["field"] in ("debit", "credit", "total"):
                sheet.write_number(
                    row,
                    col_pos,
                    self._round_value_by_currency(grand_total[column["field"]]),
                    formats["format_amount_bold"],
                )
        sheet.write_string(row, label_col, _("TOTAL"), formats["format_right"])
        report_data["row_pos"] += 1
