from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


class _Rollback(Exception):
    pass


@tagged("post_install", "-at_install")
class TestAccountSummaryJob(IvessAccountingSummaryTestCommon):
    """El cierre en segundo plano (por tandas) tiene que dejar lo mismo que el
    cierre que se hace en el momento."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoices = cls.env["account.move"]
        for index in range(8):
            partner = cls.partner_a if index % 2 else cls.partner_b
            cls.invoices |= cls._create_receivable_move(
                partner, 100.0 * (index + 1), f"2024-03-{index + 2:02d}"
            )
        # Una factura cobrada en parte (queda saldo abierto) y otra cobrada
        # del todo (va a la cuenta puente).
        cls.partial = cls._create_receivable_move(cls.partner_a, 1000.0, "2024-03-12")
        cls._collect(cls.partial, 400.0, "2024-03-20")
        cls.collected = cls._create_receivable_move(cls.partner_b, 2000.0, "2024-03-13")
        cls._collect(cls.collected, 2000.0, "2024-03-21")

    @classmethod
    def _collect(cls, invoice, amount, date):
        collection = cls.env["account.move"].create(
            {
                "journal_id": cls.operational_journal.id,
                "date": date,
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": cls.receivable_account.id,
                            "partner_id": invoice.line_ids.partner_id.id,
                            "debit": 0.0,
                            "credit": amount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": cls.revenue_account.id,
                            "debit": amount,
                            "credit": 0.0,
                        },
                    ),
                ],
            }
        )
        collection.action_post()
        (
            cls._receivable_line_of(invoice) | cls._receivable_line_of(collection)
        ).reconcile()
        return collection

    @classmethod
    def _receivable_line_of(cls, move):
        return move.line_ids.filtered(lambda line: line.account_id == cls.receivable_account)

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

    def _set_params(self, **params):
        for key, value in params.items():
            self.env["ir.config_parameter"].sudo().set_param(
                f"ivess_accounting_summary.{key}", str(value)
            )

    @staticmethod
    def _signature(move):
        return sorted(
            (
                line.account_id.id,
                line.partner_id.id,
                line.x_origin_document_id.id,
                round(line.debit, 2),
                round(line.credit, 2),
            )
            for line in move.line_ids
        )

    def _run_job(self, job, max_cycles=60):
        Job = self.env["ivess.accounting.summary.job"]
        for _cycle in range(max_cycles):
            Job._cron_process_jobs()
            job.invalidate_recordset()
            if job.state in ("done", "error"):
                break
        return job

    def _expected_signature(self):
        """Resultado del cierre en el momento, deshecho para poder repetirlo."""
        try:
            with self.env.cr.savepoint():
                wizard = self._make_wizard().with_context(summary_force_sync=True)
                wizard.action_generate_summary()
                signature = self._signature(wizard.summary_move_id)
                raise _Rollback()
        except _Rollback:
            pass
        self.env.invalidate_all()
        return signature

    def _queue_job(self):
        self._set_params(sync_line_limit=0, chunk_lines=4, legal_slice_lines=3, mark_slice_moves=2)
        action = self._make_wizard().action_generate_summary()
        self.assertEqual(action["res_model"], "ivess.accounting.summary.job")
        return self.env["ivess.accounting.summary.job"].browse(action["res_id"])

    def test_job_result_matches_closing_done_in_the_moment(self):
        expected = self._expected_signature()
        job = self._queue_job()
        self.assertEqual(job.state, "queued")
        self._run_job(job)

        self.assertEqual(job.state, "done", job.error_message)
        self.assertTrue(job.summary_move_id)
        self.assertEqual(job.summary_move_id.state, "posted")
        self.assertEqual(job.summary_move_id.journal_id, self.legal_journal)
        # Con tandas de 4 líneas hubo varios cortes, y el resultado es el mismo.
        self.assertGreater(job.chunks_done, 1)
        self.assertEqual(self._signature(job.summary_move_id), expected)
        self.assertTrue(
            self.currency.is_zero(sum(job.summary_move_id.line_ids.mapped("balance")))
        )
        self.assertEqual(job.processed_lines, job.total_lines)
        # Todo comprobante con deuda queda trazado hacia el asiento resumen.
        for invoice in self.invoices | self.partial | self.collected:
            self.assertEqual(invoice.x_closed_by_summary_move_id, job.summary_move_id)
        # Las deudas abiertas quedan conciliadas contra su neteo.
        for invoice in self.invoices | self.partial:
            self.assertTrue(
                self.currency.is_zero(self._receivable_line_of(invoice).amount_residual)
            )
        self.assertGreater(len(job.netting_move_ids), 1)

    def test_job_error_can_be_retried_without_repeating_work(self):
        expected = self._expected_signature()
        job = self._queue_job()
        Job = type(self.env["ivess.accounting.summary.job"])
        original = Job._store_contrib
        calls = {"count": 0}

        def failing_second_chunk(record, contrib):
            calls["count"] += 1
            if calls["count"] == 2:
                raise UserError("falla simulada")
            return original(record, contrib)

        with patch.object(Job, "_store_contrib", failing_second_chunk):
            self._run_job(job)

        self.assertEqual(job.state, "error")
        self.assertEqual(job.retry_state, "closing")
        self.assertIn("falla simulada", job.error_message)
        done_before = job.processed_lines
        self.assertGreater(done_before, 0)
        self.assertLess(done_before, job.total_lines)

        job.action_retry()
        self.assertEqual(job.state, "closing")
        self._run_job(job)
        self.assertEqual(job.state, "done", job.error_message)
        self.assertEqual(self._signature(job.summary_move_id), expected)
        # Lo hecho antes del error no se repitió: cada línea se procesó una vez.
        self.assertEqual(job.processed_lines, job.total_lines)

    def test_job_blocks_a_second_closing_over_the_same_period(self):
        self._queue_job()
        with self.assertRaises(UserError):
            self._make_wizard().action_generate_summary()

    def test_enqueue_validates_unmapped_debt_accounts_upfront(self):
        unmapped = self.receivable_account.copy(
            {"code": "TEST.1.1.UNMAPPED", "name": "Deudores sin Cuenta Legal - Test"}
        )
        unmapped.x_legal_debt_account_id = False
        self.env["account.move"].create(
            {
                "journal_id": self.operational_journal.id,
                "date": "2024-03-25",
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": unmapped.id,
                            "partner_id": self.partner_a.id,
                            "debit": 50.0,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.revenue_account.id,
                            "debit": 0.0,
                            "credit": 50.0,
                        },
                    ),
                ],
            }
        ).action_post()
        self._set_params(sync_line_limit=0)
        with self.assertRaises(UserError):
            self._make_wizard().action_generate_summary()
        self.assertFalse(self.env["ivess.accounting.summary.job"].search([]))

    def test_small_closing_still_runs_in_the_moment(self):
        self._set_params(sync_line_limit=1000)
        wizard = self._make_wizard()
        wizard.action_generate_summary()
        self.assertTrue(wizard.summary_move_id)
        self.assertFalse(self.env["ivess.accounting.summary.job"].search([]))
