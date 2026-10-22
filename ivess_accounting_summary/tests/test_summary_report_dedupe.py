from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestSummaryReportDedupe(IvessAccountingSummaryTestCommon):
    """Proveedores pagados: no duplicar información en diario y mayor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.payable = env["account.account"].create(
            {
                "code": "TEST.2.1.1",
                "name": "Proveedores - Test",
                "account_type": "liability_payable",
                "reconcile": True,
            }
        )
        cls.expense = env["account.account"].create(
            {"code": "TEST.5.1.1", "name": "Gastos - Test", "account_type": "expense"}
        )
        bank = env["account.account"].create(
            {"code": "TEST.1.1.2", "name": "Banco - Test", "account_type": "asset_current"}
        )
        cls.payable.x_legal_debt_account_id = cls.payable.copy(
            {"code": "TEST.2.1.1.L", "name": "Proveedores Legal - Test"}
        )
        cls.payable.x_legal_bridge_account_id = env["account.account"].create(
            {
                "code": "TEST.2.1.1.P",
                "name": "Puente Pagado - Test",
                "account_type": "liability_current",
            }
        )
        cls.bank_journal = env["account.journal"].create(
            {"name": "Banco - Test", "type": "general", "code": "TBNK", "due_date": "2020-01-01"}
        )

        def make(journal, date, lines):
            move = env["account.move"].create(
                {
                    "journal_id": journal.id,
                    "date": date,
                    "move_type": "entry",
                    "line_ids": [(0, 0, line) for line in lines],
                }
            )
            move.action_post()
            return move

        def bill(partner, amount, date):
            return make(
                cls.operational_journal,
                date,
                [
                    {"account_id": cls.expense.id, "debit": amount, "credit": 0.0},
                    {
                        "account_id": cls.payable.id,
                        "partner_id": partner.id,
                        "debit": 0.0,
                        "credit": amount,
                    },
                ],
            )

        def payment(partner, amount, date):
            return make(
                cls.bank_journal,
                date,
                [
                    {
                        "account_id": cls.payable.id,
                        "partner_id": partner.id,
                        "debit": amount,
                        "credit": 0.0,
                    },
                    {"account_id": bank.id, "debit": 0.0, "credit": amount},
                ],
            )

        def pay_line(move):
            return move.line_ids.filtered(lambda ln: ln.account_id == cls.payable)

        cls.bill_paid = bill(cls.partner_a, 500.0, "2024-03-10")
        cls.payment = payment(cls.partner_a, 500.0, "2024-03-12")
        (pay_line(cls.bill_paid) | pay_line(cls.payment)).reconcile()
        cls.bill_open_a = bill(cls.partner_a, 300.0, "2024-03-20")
        cls.bill_open_b = bill(cls.partner_b, 200.0, "2024-03-22")
        env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, cls.operational_journal.ids)],
                "legal_journal_id": cls.legal_journal.id,
            }
        ).action_generate_summary()
        cls.summary = cls.bill_paid.x_closed_by_summary_move_id
        # Pago posterior al cierre: se asienta contra la deuda legal del
        # asiento resumen (la factura original ya quedó conciliada con el
        # neteo), así que no forma parte del resumen.
        legal_account = cls.payable.x_legal_debt_account_id
        cls.late_payment = make(
            cls.bank_journal,
            "2024-04-05",
            [
                {
                    "account_id": legal_account.id,
                    "partner_id": cls.partner_a.id,
                    "debit": 300.0,
                    "credit": 0.0,
                },
                {"account_id": bank.id, "debit": 0.0, "credit": 300.0},
            ],
        )
        legal_debt = cls.summary.line_ids.filtered(
            lambda ln: ln.account_id == legal_account and ln.partner_id == cls.partner_a
        )
        (legal_debt | cls.late_payment.line_ids.filtered(
            lambda ln: ln.account_id == legal_account
        )).reconcile()

    def _journal_values(self):
        wizard = self.env["journal.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "move_target": "posted",
                "only_summary_entries": True,
                "journal_ids": [
                    (
                        6,
                        0,
                        (
                            self.operational_journal
                            | self.legal_journal
                            | self.bank_journal
                        ).ids,
                    )
                ],
            }
        )
        return self.env["report.account_financial_report.journal_ledger"]._get_report_values(
            wizard, wizard._prepare_report_data()
        )

    def test_journal_hides_absorbed_payment_keeps_late_one(self):
        values = self._journal_values()
        move_ids = {move["move_id"] for move in values["Moves"]}
        self.assertIn(self.summary.id, move_ids)
        self.assertNotIn(self.bill_paid.id, move_ids)
        self.assertNotIn(self.payment.id, move_ids)
        self.assertIn(self.late_payment.id, move_ids)

    def test_journal_summary_one_line_per_account(self):
        values = self._journal_values()
        summary = next(m for m in values["Moves"] if m["move_id"] == self.summary.id)
        account_ids = [line["account_id"] for line in summary["report_move_lines"]]
        self.assertEqual(len(account_ids), len(set(account_ids)))
        # La deuda por comprobante se colapsa con la leyenda del asiento.
        debt_line = next(
            ln
            for ln in summary["report_move_lines"]
            if ln["account_id"] == self.payable.x_legal_debt_account_id.id
        )
        self.assertTrue(debt_line["label"].startswith("Resumen Global"))
        self.assertAlmostEqual(
            sum(ln["debit"] - ln["credit"] for ln in summary["report_move_lines"]),
            0.0,
        )

    def test_general_ledger_hides_absorbed_payment(self):
        wizard = self.env["general.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "target_move": "posted",
                "only_summary_entries": True,
            }
        )
        lines = self.env["account.move.line"].search(
            wizard._get_account_move_lines_domain()
        )
        self.assertNotIn(self.payment, lines.move_id)
        self.assertIn(self.late_payment, lines.move_id)
        self.assertEqual(wizard._prepare_report_data()["grouped_by"], "none")

    def test_general_ledger_summary_one_line_per_account(self):
        wizard = self.env["general.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "target_move": "posted",
                "only_summary_entries": True,
            }
        )
        data = wizard._prepare_report_data()
        values = self.env["report.account_financial_report.general_ledger"]._get_report_values(
            wizard, data
        )
        for account in values["general_ledger"]:
            entries = [
                line["entry_id"]
                for line in account["move_lines"]
                if line["entry_id"] == self.summary.id
            ]
            self.assertLessEqual(len(entries), 1, account["code"])

    def _html(self, wizard, report_name):
        html = self.env["ir.actions.report"]._render_qweb_html(
            report_name, [wizard.id], data=wizard._prepare_report_data()
        )[0]
        return html.decode() if isinstance(html, bytes) else html

    def test_general_ledger_html_renders_one_summary_row_per_account(self):
        wizard = self.env["general.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "target_move": "posted",
                "only_summary_entries": True,
            }
        )
        html = self._html(wizard, "account_financial_report.general_ledger")
        self.assertIn(self.summary.name, html)
        self.assertNotIn(self.bill_paid.name, html)
        self.assertEqual(html.count(self.summary.name), len(self._summary_accounts()))

    def _summary_accounts(self):
        # Una fila por cuenta con movimientos del asiento resumen.
        return self.summary.line_ids.account_id

    def test_journal_ledger_html_and_general_ledger_xlsx_render(self):
        import io

        import xlsxwriter

        journal = self.env["journal.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "move_target": "posted",
                "only_summary_entries": True,
                "journal_ids": [
                    (6, 0, (self.operational_journal | self.legal_journal).ids)
                ],
            }
        )
        self.assertIn(
            self.summary.name,
            self._html(journal, "account_financial_report.journal_ledger"),
        )
        mayor = self.env["general.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-04-30",
                "target_move": "posted",
                "only_summary_entries": True,
            }
        )
        workbook = xlsxwriter.Workbook(
            io.BytesIO(), {"in_memory": True, "constant_memory": True}
        )
        self.env["report.a_f_r.report_general_ledger_xlsx"].generate_xlsx_report(
            workbook, mayor._prepare_report_data(), mayor
        )
        self.assertTrue(workbook.worksheets())
        workbook.close()
