from unittest.mock import patch

from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon

FULL_RECONCILE = (
    "odoo.addons.l10n_ar_reconciliation.models.account_full_reconcile."
    "AccountFullReconcile._update_checks_on_reconcile"
)


@tagged("post_install", "-at_install")
class TestSummaryPerformanceShortcuts(IvessAccountingSummaryTestCommon):
    """Los atajos de rendimiento del cierre no pueden cambiar lo que hace."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["ivess.accounting.summary.wizard"].create(
            {
                "company_id": cls.env.company.id,
                "date_from": "2024-03-01",
                "date_to": "2024-03-31",
                "operational_journal_ids": [(6, 0, cls.operational_journal.ids)],
                "legal_journal_id": cls.legal_journal.id,
            }
        )

    def test_mark_sets_field_and_refreshes_cache(self):
        invoice = self._create_receivable_move(self.partner_a, 100.0, "2024-03-05")
        marker = self._create_receivable_move(self.partner_b, 50.0, "2024-03-06")
        lines = invoice.line_ids
        self.assertFalse(lines.x_summary_move_id)
        self.engine._summary_mark(lines, "x_summary_move_id", marker)
        self.assertEqual(lines.x_summary_move_id, marker)
        self.env.invalidate_all()
        self.assertEqual(lines.x_summary_move_id, marker)
        self.assertEqual(lines.write_uid, self.env.user)

    def test_mark_move_field(self):
        invoice = self._create_receivable_move(self.partner_a, 100.0, "2024-03-05")
        marker = self._create_receivable_move(self.partner_b, 50.0, "2024-03-06")
        self.engine._summary_mark(invoice, "x_closed_by_summary_move_id", marker)
        self.env.invalidate_all()
        self.assertEqual(invoice.x_closed_by_summary_move_id, marker)

    def test_mark_empty_does_nothing(self):
        self.engine._summary_mark(
            self.env["account.move.line"], "x_summary_move_id", self.env["account.move"]
        )

    def test_line_defaults_depend_on_distribution_models(self):
        Model = self.env["account.analytic.distribution.model"]
        Model.search([]).unlink()
        self.assertEqual(
            self.engine._summary_entry_line_defaults(), {"analytic_distribution": False}
        )
        plan = self.env["account.analytic.plan"].create({"name": "Plan test"})
        account = self.env["account.analytic.account"].create(
            {"name": "Cuenta test", "plan_id": plan.id}
        )
        Model.create({"analytic_distribution": {str(account.id): 100.0}})
        self.assertEqual(self.engine._summary_entry_line_defaults(), {})

    def test_check_shortcut(self):
        invoice = self._create_receivable_move(self.partner_a, 100.0, "2024-03-05")
        collection = self._create_receivable_move(self.partner_a, -100.0, "2024-03-06")
        (
            self._receivable_line(invoice) | self._receivable_line(collection)
        ).reconcile()
        full = self._receivable_line(invoice).full_reconcile_id
        self.assertTrue(full)
        move_ids = set(full.reconciled_line_ids.move_id.ids)

        with patch(FULL_RECONCILE, autospec=True) as original:
            # Sin asientos con cheques: no se revisa.
            full.with_context(
                ivess_summary_check_move_ids=frozenset()
            )._update_checks_on_reconcile()
            full.with_context(
                ivess_summary_check_move_ids=frozenset({0})
            )._update_checks_on_reconcile()
            original.assert_not_called()
            # Si alguno de sus asientos tiene cheques: se revisa como siempre.
            full.with_context(
                ivess_summary_check_move_ids=frozenset(move_ids)
            )._update_checks_on_reconcile()
            self.assertEqual(original.call_count, 1)
            # Fuera del cierre (sin la clave) tampoco cambia nada.
            full._update_checks_on_reconcile()
            self.assertEqual(original.call_count, 2)

    def test_check_move_ids_include_issued_checks(self):
        invoice = self._create_receivable_move(self.partner_a, 100.0, "2024-03-05")
        self.env.cr.execute(
            "SELECT DISTINCT move_id FROM account_move_line WHERE issued_check_id IS NOT NULL"
        )
        expected = {row[0] for row in self.env.cr.fetchall()}
        result = self.engine._summary_check_move_ids()
        self.assertTrue(expected <= result)
        self.assertNotIn(invoice.id, result)
