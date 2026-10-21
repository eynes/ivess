from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestGeneralLedgerIvess(IvessAccountingSummaryTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_a = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-15")
        cls.invoice_b = cls._create_receivable_move(cls.partner_b, 2000.0, "2024-03-20")

    def _make_ledger_wizard(self, **vals):
        return self.env["general.ledger.report.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "target_move": "posted",
                **vals,
            }
        )

    def _move_ids(self, wizard):
        domain = wizard._get_account_move_lines_domain()
        return set(self.env["account.move.line"].search(domain).move_id.ids)

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

    def test_only_summary_entries_hides_summarized_moves(self):
        self._close_month()
        everything = self._move_ids(self._make_ledger_wizard())
        only_summary = self._move_ids(
            self._make_ledger_wizard(only_summary_entries=True)
        )
        summary_moves = self.env["account.move"].browse(only_summary)
        # Se ven los asientos resumen del Diario Legal...
        self.assertTrue(summary_moves)
        self.assertEqual(summary_moves.journal_id, self.legal_journal)
        # ...y no los comprobantes resumidos ni sus asientos de neteo.
        self.assertNotIn(self.invoice_a.id, only_summary)
        self.assertNotIn(self.invoice_b.id, only_summary)
        self.assertTrue({self.invoice_a.id, self.invoice_b.id} <= everything)

    def test_option_off_keeps_everything(self):
        self._close_month()
        move_ids = self._move_ids(self._make_ledger_wizard())
        self.assertTrue({self.invoice_a.id, self.invoice_b.id} <= move_ids)
