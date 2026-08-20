from odoo.tests.common import tagged

from .common import TestInternalVoucherCommon


@tagged('post_install', '-at_install')
class TestAccountJournal(TestInternalVoucherCommon):
    def test_fiscal_type_selection_has_internal_voucher(self):
        field = self.env['account.journal']._fields['fiscal_type']
        selection = dict(field._description_selection(self.env))
        self.assertIn('internal_voucher', selection)

    def test_journal_created_with_internal_voucher(self):
        self.assertEqual(
            self.internal_voucher_journal.fiscal_type, 'internal_voucher'
        )
