from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import TestInternalVoucherCommon


@tagged('post_install', '-at_install')
class TestArbaPerceptionExporter(TestInternalVoucherCommon):
    def _create_wizard(self):
        return self.env['arba.perception.exporter.wizard'].create(
            {
                'company_id': self.env.company.id,
                'date_from': fields.Date.today(),
                'date_to': fields.Date.today(),
            }
        )

    def test_create_file_excludes_internal_voucher_perception(self):
        normal_invoice = self._create_invoice(
            self.normal_journal
        )
        normal_invoice.action_post()
        normal_perception = self._create_perception(
            normal_invoice, self.arba_tax
        )

        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.action_post()
        internal_perception = self._create_perception(
            internal_invoice, self.arba_tax
        )

        wizard = self._create_wizard()
        with patch.object(
            type(wizard), '_generate_perception_file'
        ) as mock_generate:
            wizard.create_file()

        mock_generate.assert_called_once()
        exported_ids = mock_generate.call_args.args[0]
        self.assertIn(normal_perception.id, exported_ids)
        self.assertNotIn(internal_perception.id, exported_ids)

    def test_create_file_raises_when_only_internal_voucher_perception(self):
        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.action_post()
        self._create_perception(internal_invoice, self.arba_tax)

        wizard = self._create_wizard()
        with self.assertRaises(ValidationError):
            wizard.create_file()
