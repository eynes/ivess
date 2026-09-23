from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestJournalManualDocumentNumber(TransactionCase):
    """Customer invoice manual numbering, forced per journal.

    Uses plain in-memory (`.new()`) records and a TransactionCase instead of
    AccountTestInvoicingCommon on purpose: that common base creates a
    company-independent partner during setUpClass, and in this codebase that
    currently crashes (l10n_ar_padron_ws_consumer's res.partner create hook
    calls out to the AFIP padron webservice unconditionally on every
    res.partner creation).

    These are unit tests on the two hooks the fix relies on
    (``AccountJournal.get_sequence_from_invoice`` and
    ``AccountMove._required_internal_number``), not a full post() of a real
    invoice: driving `_post()` end to end needs AR-specific setup (fiscal
    position, denomination, journal due date, taxes) that isn't safe to
    guess here. See the task documentation for the manual UI check that
    covers the full posting flow.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _new_journal(self, force_manual):
        return self.env["account.journal"].new(
            {
                "name": "Test Sale Journal",
                "code": "TSJ",
                "type": "sale",
                "company_id": self.company.id,
                "ivess_force_manual_document_number": force_manual,
            }
        )

    def test_get_sequence_from_invoice_returns_manual_stub(self):
        journal = self._new_journal(force_manual=True)
        move = self.env["account.move"].new(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "internal_number": "0001-00001234",
            }
        )
        sequence = journal.get_sequence_from_invoice(move)
        self.assertEqual(sequence._next(), "0001-00001234")

    def test_get_sequence_from_invoice_falls_back_when_not_forced(self):
        journal = self._new_journal(force_manual=False)
        move = self.env["account.move"].new(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
            }
        )
        # Without the flag, the real (l10n_ar_eynes) sequence resolution runs: a
        # plain sale journal's sequence_id field, not our manual stand-in.
        sequence = journal.get_sequence_from_invoice(move)
        self.assertNotIsInstance(sequence, type(None))
        self.assertEqual(sequence, journal.sequence_id)

    def test_get_sequence_from_invoice_ignores_vendor_bills(self):
        journal = self._new_journal(force_manual=True)
        move = self.env["account.move"].new(
            {
                "move_type": "in_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
            }
        )
        # The flag only targets customer invoices/refunds, a vendor bill on
        # the same (sale-type) journal must not be forced through it.
        sequence = journal.get_sequence_from_invoice(move)
        self.assertNotEqual(type(sequence).__name__, "_ManualDocumentSequence")

    def test_required_internal_number_blocks_posting_without_value(self):
        journal = self._new_journal(force_manual=True)
        move = self.env["account.move"].new(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "internal_number": False,
            }
        )
        with self.assertRaises(ValidationError):
            move._required_internal_number()

    def test_required_internal_number_allows_posting_with_value(self):
        journal = self._new_journal(force_manual=True)
        move = self.env["account.move"].new(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "internal_number": "0001-00001234",
            }
        )
        move._required_internal_number()  # should not raise

    def test_required_internal_number_ignores_journals_without_flag(self):
        journal = self._new_journal(force_manual=False)
        move = self.env["account.move"].new(
            {
                "move_type": "out_invoice",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "internal_number": False,
            }
        )
        move._required_internal_number()  # should not raise
