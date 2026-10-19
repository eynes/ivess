from unittest.mock import patch

from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestRetentionSummarizedDebt(IvessAccountingSummaryTestCommon):
    """La deuda resumida debe retener sobre el comprobante de origen."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-15")
        cls.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": cls.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, cls.operational_journal.ids)],
                "legal_journal_id": cls.legal_journal.id,
            }
        ).action_generate_summary()
        cls.summary = cls.invoice.x_closed_by_summary_move_id
        cls.debt_line = cls.summary.line_ids.filtered(
            lambda ln: ln.x_origin_document_id == cls.invoice
        )

    def test_summary_debt_line_has_origin(self):
        self.assertTrue(self.summary.x_is_summary_entry)
        self.assertEqual(len(self.debt_line), 1)

    def test_payment_order_line_points_to_origin_document(self):
        order = self.env["account.payment.order"].new(
            {"currency_id": self.env.company.currency_id.id}
        )
        lines = order._prepare_income_debt_lines("debt", self.debt_line)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["move_line_id"], self.debt_line.id)
        self.assertEqual(lines[0]["invoice_id"], self.invoice.id)
        self.assertEqual(lines[0]["name"], self.invoice.name)

    def test_retention_base_uses_origin_document(self):
        target = (
            "odoo.addons.l10n_ar_eynes.models.account_tax."
            "AccountTax._compute_base_retention"
        )
        with patch(target, return_value={}) as mocked:
            self.env["account.tax"]._compute_base_retention(
                self.env["account.payment.order"], self.debt_line, 1.0, 1.0, [], "debt", None
            )
        passed_line = mocked.call_args.args[1]
        self.assertEqual(passed_line.move_id, self.invoice)
