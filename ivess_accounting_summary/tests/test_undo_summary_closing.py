from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestUndoSummaryClosing(IvessAccountingSummaryTestCommon):
    """Borrar el asiento resumen deshace el cierre completo, de modo que los
    comprobantes vuelven a poder resumirse (T15837, razón de revisión 1158)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_a = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-15")
        cls.invoice_b = cls._create_receivable_move(cls.partner_b, 2000.0, "2024-03-20")

    def _close(self):
        wizard = self.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": self.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, self.operational_journal.ids)],
                "legal_journal_id": self.legal_journal.id,
            }
        )
        wizard.action_generate_summary()
        return wizard.summary_move_id, wizard.netting_move_ids

    def _assert_back_to_original(self):
        for invoice in (self.invoice_a, self.invoice_b):
            self.assertFalse(invoice.x_closed_by_summary_move_id)
            line = self._receivable_line(invoice)
            self.assertFalse(line.x_summary_move_id)
            self.assertFalse(line.reconciled)
            self.assertEqual(line.amount_residual, line.balance)
            self.assertEqual(invoice.payment_state, "not_paid")

    def test_unlink_summary_move_undoes_the_closing_and_allows_a_new_one(self):
        summary, netting = self._close()
        netting_ids = netting.ids
        summary.button_draft()
        # Borrado manual: pide confirmar con las cantidades y no borra nada.
        with self.assertRaises(RedirectWarning) as ctx:
            summary.unlink()
        self.assertIn("2 comprobantes", str(ctx.exception))
        self.assertTrue(summary.exists())
        summary.with_context(ivess_undo_confirmed=True).unlink()

        self.assertFalse(self.env["account.move"].browse(netting_ids).exists())
        self._assert_back_to_original()

        new_summary, new_netting = self._close()
        self.assertTrue(new_summary)
        self.assertEqual(self.invoice_a.x_closed_by_summary_move_id, new_summary)

    def test_undo_button_action(self):
        summary, _netting = self._close()
        self.assertTrue(summary.x_is_legal_summary_entry)
        self.assertFalse(_netting.x_is_legal_summary_entry)
        action = summary.action_undo_summary_closing()
        wizard = (
            self.env[action["res_model"]]
            .with_context(**action["context"])
            .create({})
        )
        self.assertEqual((wizard.closed_count, wizard.netting_count), (2, 1))
        wizard.action_confirm()
        self.assertFalse(summary.exists())
        self._assert_back_to_original()

    def test_undo_blocked_with_folio(self):
        summary, _netting = self._close()
        summary.x_folio_legal = "1"
        with self.assertRaises(UserError):
            summary.action_undo_summary_closing()
        summary.button_draft()
        with self.assertRaises(UserError):
            summary.unlink()
        self.assertTrue(summary.exists())
        self.assertEqual(self.invoice_a.x_closed_by_summary_move_id, summary)

    def test_undo_blocked_with_payment_on_debt_line(self):
        summary, _netting = self._close()
        debt_line = summary.line_ids.filtered(
            lambda line: line.account_id == self.legal_debt_account
            and line.partner_id == self.partner_a
        )
        payment = self.env["account.move"].create(
            {
                "journal_id": self.operational_journal.id,
                "date": "2024-04-05",
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.legal_debt_account.id,
                            "partner_id": self.partner_a.id,
                            "debit": 0.0,
                            "credit": 1000.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.revenue_account.id,
                            "debit": 1000.0,
                            "credit": 0.0,
                        },
                    ),
                ],
            }
        )
        payment.action_post()
        pay_line = payment.line_ids.filtered(
            lambda line: line.account_id == self.legal_debt_account
        )
        (debt_line | pay_line).reconcile()
        with self.assertRaises(UserError):
            summary.action_undo_summary_closing()

    def test_orphan_closing_is_recovered(self):
        """Cierre cuyo asiento legal ya se había borrado sin deshacer."""
        summary, netting = self._close()
        self.env.cr.execute(
            "UPDATE account_move SET x_closed_by_summary_move_id = NULL "
            "WHERE x_closed_by_summary_move_id = %s",
            [summary.id],
        )
        self.env["account.move"].invalidate_model(["x_closed_by_summary_move_id"])
        summary.button_draft()
        summary.unlink()

        self.assertEqual(
            self.env["account.move"]._ivess_orphan_summary_netting_moves(), netting
        )
        self.env["account.move"]._ivess_undo_orphan_summary_closings()
        self._assert_back_to_original()
