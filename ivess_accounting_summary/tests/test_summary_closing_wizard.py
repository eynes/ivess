from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestAccountSummaryClosingWizard(IvessAccountingSummaryTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_a = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-15")
        cls.invoice_b = cls._create_receivable_move(cls.partner_b, 2000.0, "2024-03-20")

    def _make_wizard(self):
        return self.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, self.operational_journal.ids)],
                "legal_journal_id": self.legal_journal.id,
            }
        )

    def test_generate_summary_nets_and_creates_legal_debt(self):
        wizard = self._make_wizard()
        wizard.action_generate_summary()

        self.assertTrue(wizard.summary_move_id)
        self.assertEqual(wizard.summary_move_id.journal_id, self.legal_journal)
        self.assertTrue(wizard.summary_move_id.x_is_summary_entry)
        self.assertEqual(wizard.summary_move_id.state, "posted")

        # Las facturas quedan totalmente conciliadas (Cerradas por Resumen).
        line_a = self._receivable_line(self.invoice_a)
        line_b = self._receivable_line(self.invoice_b)
        self.assertTrue(self.currency.is_zero(line_a.amount_residual))
        self.assertTrue(self.currency.is_zero(line_b.amount_residual))
        self.assertEqual(
            self.invoice_a.x_closed_by_summary_move_id, wizard.summary_move_id
        )
        self.assertEqual(
            self.invoice_b.x_closed_by_summary_move_id, wizard.summary_move_id
        )

        # El asiento legal trae una línea de deuda por factura, trazable a su origen.
        debt_lines = wizard.summary_move_id.line_ids.filtered(
            lambda line: line.account_id == self.legal_debt_account
        )
        self.assertEqual(
            set(debt_lines.mapped("x_origin_document_id")),
            {self.invoice_a, self.invoice_b},
        )
        self.assertAlmostEqual(sum(debt_lines.mapped("debit")), 1000.0 + 2000.0)

        # Partida doble: el asiento legal y el neteo operativo quedan balanceados.
        summary_balance = sum(wizard.summary_move_id.line_ids.mapped("balance"))
        self.assertTrue(self.currency.is_zero(summary_balance))
        self.assertEqual(len(wizard.netting_move_ids), 1)
        netting_balance = sum(wizard.netting_move_ids.line_ids.mapped("balance"))
        self.assertTrue(self.currency.is_zero(netting_balance))

        # El diario operativo queda neteado a cero en la cuenta de resultado.
        revenue_balance = sum(
            self.env["account.move.line"]
            .search(
                [
                    ("journal_id", "=", self.operational_journal.id),
                    ("account_id", "=", self.revenue_account.id),
                    ("date", ">=", "2024-03-01"),
                    ("date", "<=", "2024-03-31"),
                ]
            )
            .mapped("balance")
        )
        self.assertTrue(self.currency.is_zero(revenue_balance))

    def test_generate_summary_twice_does_not_duplicate(self):
        wizard = self._make_wizard()
        wizard.action_generate_summary()

        with self.assertRaises(UserError):
            self._make_wizard().action_generate_summary()

    def test_generate_summary_requires_valid_period(self):
        wizard = self.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-31",
                "date_to": "2024-03-01",
                "operational_journal_ids": [(6, 0, self.operational_journal.ids)],
                "legal_journal_id": self.legal_journal.id,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_generate_summary()

    def test_partial_payment_only_open_residual_is_summarized(self):
        # Cobro parcial de la factura A antes del cierre: solo el saldo
        # pendiente (no el total original) debe viajar a la deuda legal.
        collection_move = self.env["account.move"].create(
            {
                "journal_id": self.operational_journal.id,
                "date": "2024-03-25",
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.receivable_account.id,
                            "partner_id": self.partner_a.id,
                            "debit": 0.0,
                            "credit": 500.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.revenue_account.id,
                            "debit": 500.0,
                            "credit": 0.0,
                        },
                    ),
                ],
            }
        )
        collection_move.action_post()
        invoice_line = self._receivable_line(self.invoice_a)
        collection_line = self._receivable_line(collection_move)
        (invoice_line | collection_line).reconcile()

        wizard = self._make_wizard()
        wizard.action_generate_summary()

        debt_line = wizard.summary_move_id.line_ids.filtered(
            lambda line: line.x_origin_document_id == self.invoice_a
        )
        self.assertAlmostEqual(sum(debt_line.mapped("debit")), 500.0)
