from odoo import fields
from odoo.tests.common import tagged

from .common import TestInternalVoucherCommon


@tagged('post_install', '-at_install')
class TestAccountMove(TestInternalVoucherCommon):
    def test_post_internal_voucher_skips_electronic_validation(self):
        """A journal internal_voucher must behave like internal: no CAE,
        manual sequence assigned on post, same as the existing 'internal'
        fiscal_type."""
        invoice = self._create_invoice(self.internal_voucher_journal)
        invoice.action_post()

        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.internal_number)
        self.assertFalse(invoice.cae)

    def test_report_xls_query_extra_excludes_internal_voucher(self):
        (
            select_extra,
            join_extra,
            where_extra,
            sort_selection,
        ) = self.env['account.move']._report_xls_query_extra()
        self.assertIn('internal_voucher', where_extra)

    def test_sales_by_jurisdiction_excludes_internal_voucher(self):
        normal_invoice = self._create_invoice(
            self.normal_journal
        )
        normal_invoice.action_post()

        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.action_post()

        report_model = self.env[
            'report.l10n_ar_eynes.sales_by_jurisdiction_export_xlsx'
        ]
        lines = report_model.get_data(
            {
                'date_start': fields.Date.today(),
                'date_stop': fields.Date.today(),
            },
            self.env.company.id,
            'sale',
        )
        invoice_ids = {line['invoice_id'] for line in lines}

        self.assertIn(normal_invoice.id, invoice_ids)
        self.assertNotIn(internal_invoice.id, invoice_ids)
