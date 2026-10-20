from unittest.mock import patch

from odoo import fields
from odoo.tests.common import tagged

from .common import TestInternalVoucherCommon


@tagged('post_install', '-at_install')
class TestCreateLibroIva(TestInternalVoucherCommon):
    """libro.iva.exporter.wizard: internal vouchers are not exported."""

    def _create_wizard(self, file_format):
        return self.env['libro.iva.exporter.wizard'].create(
            {
                'company_id': self.env.company.id,
                'date_from': fields.Date.today().replace(day=1),
                'date_to': fields.Date.today(),
                'file_format': file_format,
            }
        )

    def _exported_invoices(self, file_format, method, invoices):
        wizard = self._create_wizard(file_format)
        base = type(wizard).__mro__[1]
        with patch.object(
            base, method, autospec=True, return_value=([], [])
        ) as mocked:
            getattr(wizard, method)(invoices)
        return mocked.call_args.args[1]

    def test_excludes_internal_voucher_from_files(self):
        normal = self._create_invoice(self.normal_journal)
        internal = self._create_invoice(self.internal_voucher_journal)
        invoices = normal | internal
        for file_format, method in (
            ('txt', 'create_sales_voucher_file'),
            ('txt', 'create_purchases_voucher_file'),
            ('xlsx', 'create_sales_voucher_file_xlsx'),
            ('xlsx', 'create_purchases_voucher_file_xlsx'),
        ):
            with self.subTest(method=method):
                exported = self._exported_invoices(
                    file_format, method, invoices
                )
                self.assertEqual(exported, normal)
