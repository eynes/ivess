from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestLegalFolioRenumberWizard(IvessAccountingSummaryTestCommon):
    def _create_balanced_move(self, journal, date):
        return self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date,
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.revenue_account.id,
                            "debit": 100.0,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.receivable_account.id,
                            "debit": 0.0,
                            "credit": 100.0,
                        },
                    ),
                ],
            }
        )

    def _make_folio_wizard(self):
        return self.env["ivess.legal.folio.renumber.wizard"].create(
            {"company_id": self.env.company.id}
        )

    def test_renumber_assigns_sequential_folio_without_gaps(self):
        move_1 = self._create_balanced_move(self.legal_journal, "2024-01-31")
        move_2 = self._create_balanced_move(self.legal_journal, "2024-02-29")
        other_move = self._create_balanced_move(self.operational_journal, "2024-01-15")
        (move_1 | move_2 | other_move).action_post()

        wizard = self._make_folio_wizard()
        wizard.action_renumber()

        self.assertEqual(wizard.renumbered_count, 2)
        self.assertEqual(move_1.x_folio_legal, "000001")
        self.assertEqual(move_2.x_folio_legal, "000002")
        self.assertFalse(other_move.x_folio_legal)

    def test_renumber_recomputes_without_gaps_after_new_earlier_entry(self):
        move_1 = self._create_balanced_move(self.legal_journal, "2024-01-31")
        move_2 = self._create_balanced_move(self.legal_journal, "2024-02-29")
        (move_1 | move_2).action_post()
        self._make_folio_wizard().action_renumber()

        # Un asiento posterior con fecha anterior (ej. Cierre de Ejercicio
        # cargado tarde) debe intercalarse sin dejar huecos al renumerar.
        move_0 = self._create_balanced_move(self.legal_journal, "2024-01-01")
        move_0.action_post()

        wizard2 = self._make_folio_wizard()
        wizard2.action_renumber()

        self.assertEqual(wizard2.renumbered_count, 3)
        self.assertEqual(move_0.x_folio_legal, "000001")
        self.assertEqual(move_1.x_folio_legal, "000002")
        self.assertEqual(move_2.x_folio_legal, "000003")
