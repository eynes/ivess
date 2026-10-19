import io

import xlsxwriter

from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestJournalLedgerIvess(IvessAccountingSummaryTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_a = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-15")
        cls.invoice_b = cls._create_receivable_move(cls.partner_b, 2000.0, "2024-03-20")

    def _make_ledger_wizard(self, **vals):
        return self.env["journal.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "journal_ids": [
                    (6, 0, (self.operational_journal | self.legal_journal).ids)
                ],
                "move_target": "posted",
                **vals,
            }
        )

    def _report_values(self, wizard):
        data = wizard._prepare_report_data()
        values = self.env[
            "report.account_financial_report.journal_ledger"
        ]._get_report_values(wizard, data)
        return values

    def _close_month(self):
        self.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, self.operational_journal.ids)],
                "legal_journal_id": self.legal_journal.id,
            }
        ).action_generate_summary()

    def test_total_column_and_grand_total(self):
        values = self._report_values(self._make_ledger_wizard())
        lines = [line for move in values["Moves"] for line in move["report_move_lines"]]
        # Débitos positivos, créditos negativos.
        for line in lines:
            self.assertAlmostEqual(line["total"], line["debit"] - line["credit"])
        self.assertTrue(any(line["total"] > 0 for line in lines))
        self.assertTrue(any(line["total"] < 0 for line in lines))
        grand_total = values["grand_total"]
        self.assertAlmostEqual(grand_total["debit"], 3000.0)
        self.assertAlmostEqual(grand_total["credit"], 3000.0)
        self.assertAlmostEqual(grand_total["total"], 0.0)

    def test_header_values(self):
        wizard = self._make_ledger_wizard()
        values = self._report_values(wizard)
        # Sin ejercicio definido cae al año de la fecha de fin.
        self.assertEqual(values["fiscal_year_name"], "2024")
        self.assertEqual(values["period_text"], "01/03/2024 A 31/03/2024")

    def test_only_summary_entries_hides_summarized_moves(self):
        self._close_month()
        everything = self._report_values(self._make_ledger_wizard())
        only_summary = self._report_values(
            self._make_ledger_wizard(only_summary_entries=True)
        )
        all_ids = {move["move_id"] for move in everything["Moves"]}
        summary_ids = {move["move_id"] for move in only_summary["Moves"]}
        summary_moves = self.env["account.move"].browse(summary_ids)
        # Se ven los asientos resumen del Diario Legal...
        self.assertTrue(summary_moves)
        self.assertEqual(summary_moves.journal_id, self.legal_journal)
        self.assertTrue(all(summary_moves.mapped("x_is_summary_entry")))
        # ...y no los comprobantes resumidos ni sus asientos de neteo.
        self.assertNotIn(self.invoice_a.id, summary_ids)
        self.assertNotIn(self.invoice_b.id, summary_ids)
        self.assertTrue({self.invoice_a.id, self.invoice_b.id} <= all_ids)
        self.assertLess(len(summary_ids), len(all_ids))

    def test_summary_option_off_keeps_everything(self):
        self._close_month()
        values = self._report_values(self._make_ledger_wizard())
        move_ids = {move["move_id"] for move in values["Moves"]}
        self.assertTrue({self.invoice_a.id, self.invoice_b.id} <= move_ids)

    def _xlsx_columns(self, wizard):
        data = wizard._prepare_report_data()
        report = self.env["report.a_f_r.report_journal_ledger_xlsx"]
        return list(report._get_report_columns(wizard).values()), report, data

    def test_xlsx_columns(self):
        columns, _report, _data = self._xlsx_columns(self._make_ledger_wizard())
        fields_ = [column["field"] for column in columns]
        self.assertNotIn("taxes_description", fields_)
        self.assertIn("partner", fields_)
        self.assertEqual(fields_[-3:], ["debit", "credit", "total"])
        columns, _report, _data = self._xlsx_columns(
            self._make_ledger_wizard(hide_partner=True)
        )
        self.assertNotIn("partner", [column["field"] for column in columns])

    def test_xlsx_single_sheet(self):
        # Con agrupación por diario el reporte original genera una hoja por
        # diario más una de impuestos por diario.
        wizard = self._make_ledger_wizard(group_option="journal")
        data = wizard._prepare_report_data()
        report = self.env["report.a_f_r.report_journal_ledger_xlsx"]
        workbook = xlsxwriter.Workbook(
            io.BytesIO(), {"in_memory": True, "constant_memory": True}
        )
        report.generate_xlsx_report(workbook, data, wizard)
        self.assertEqual(len(workbook.worksheets()), 1)
        workbook.close()
