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

    def test_vat_subjournal_excludes_internal_voucher(self):
        # The subjournal query INNER JOINs the fiscal position.
        fiscal_position = self.env.ref('l10n_ar_eynes.fiscal_position_cf')
        normal_invoice = self._create_invoice(self.normal_journal)
        normal_invoice.fiscal_position_id = fiscal_position
        normal_invoice.action_post()

        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.fiscal_position_id = fiscal_position
        internal_invoice.action_post()

        wizard = self.env['account.tax.subjournal'].create(
            {
                'date_from': fields.Date.today().replace(day=1),
                'date_to': fields.Date.today(),
                'based_on': 'sale',
            }
        )
        report_model = self.env['report.report_xlsx.move_line_list_subj']
        rows = report_model._get_line_vals(
            ['out_invoice', 'out_refund'], wizard
        )
        invoice_ids = {row['invoice_id'] for row in rows}

        self.assertIn(normal_invoice.id, invoice_ids)
        self.assertNotIn(internal_invoice.id, invoice_ids)

    def test_apportionable_vat_subjournal_excludes_internal_voucher(self):
        # The query INNER JOINs the fiscal position.
        fiscal_position = self.env.ref('l10n_ar_eynes.fiscal_position_cf')
        normal_invoice = self._create_invoice(self.normal_journal)
        normal_invoice.fiscal_position_id = fiscal_position
        # The query INNER JOINs the voucher type, set by the electronic flow.
        normal_invoice._force_voucher_type()
        normal_invoice.action_post()

        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.fiscal_position_id = fiscal_position
        internal_invoice._force_voucher_type()
        internal_invoice.action_post()

        wizard_model = self.env['account.tax.subjournal.apportionable.wizard']
        wizard = wizard_model.create(
            {
                'company_id': self.env.company.id,
                'date_from': fields.Date.today().replace(day=1),
                'date_to': fields.Date.today(),
                'based_on': 'sale',
            }
        )
        invoice_ids = {row['invoice_id'] for row in wizard._get_line_vals()}

        self.assertIn(normal_invoice.id, invoice_ids)
        self.assertNotIn(internal_invoice.id, invoice_ids)
