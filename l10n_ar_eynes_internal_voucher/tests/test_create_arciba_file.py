from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import TestInternalVoucherCommon


@tagged('post_install', '-at_install')
class TestCreateArcibaFiles(TestInternalVoucherCommon):
    """create.arciba.files: perceptions on out_invoice."""

    def _create_wizard(self):
        return self.env['create.arciba.files'].create(
            {
                'company_id': self.env.company.id,
                'period_start': fields.Date.today(),
                'period_end': fields.Date.today(),
            }
        )

    def test_create_files_excludes_internal_voucher_perception(self):
        normal_invoice = self._create_invoice(
            self.normal_journal
        )
        normal_invoice.action_post()
        normal_perception = self._create_perception(
            normal_invoice, self.arciba_tax
        )

        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.action_post()
        internal_perception = self._create_perception(
            internal_invoice, self.arciba_tax
        )

        wizard = self._create_wizard()
        with patch.object(
            type(wizard), '_get_perc_data'
        ) as mock_get_perc, patch.object(
            type(wizard), 'generate_fw_file'
        ) as mock_generate:
            mock_get_perc.return_value = (None, [{'fecha': '01/01/2026'}])
            mock_generate.return_value = True
            wizard.create_files()

        mock_get_perc.assert_called_once()
        exported_ids = mock_get_perc.call_args.args[0]
        self.assertIn(normal_perception.id, exported_ids)
        self.assertNotIn(internal_perception.id, exported_ids)

    def test_create_files_raises_when_only_internal_voucher_perception(self):
        internal_invoice = self._create_invoice(self.internal_voucher_journal)
        internal_invoice.action_post()
        self._create_perception(internal_invoice, self.arciba_tax)

        wizard = self._create_wizard()
        with self.assertRaises(ValidationError):
            wizard.create_files()


@tagged('post_install', '-at_install')
class TestCreateArcibaNcFile(TestInternalVoucherCommon):
    """create.arciba.nc.file: perceptions on out_refund."""

    def _create_wizard(self):
        return self.env['create.arciba.nc.file'].create(
            {
                'company_id': self.env.company.id,
                'period_start': fields.Date.today(),
                'period_end': fields.Date.today(),
            }
        )

    def test_create_files_excludes_internal_voucher_perception(self):
        normal_invoice = self._create_invoice(
            self.normal_journal, move_type='out_refund'
        )
        normal_invoice.action_post()
        normal_perception = self._create_perception(
            normal_invoice, self.arciba_tax
        )

        internal_invoice = self._create_invoice(
            self.internal_voucher_journal, move_type='out_refund'
        )
        internal_invoice.action_post()
        internal_perception = self._create_perception(
            internal_invoice, self.arciba_tax
        )

        wizard = self._create_wizard()
        with patch.object(
            type(wizard), '_get_inv_data'
        ) as mock_get_inv, patch.object(
            type(wizard), 'generate_fw_file'
        ) as mock_generate:
            mock_get_inv.return_value = (None, [{'fecha': '01/01/2026'}])
            mock_generate.return_value = True
            wizard.create_files()

        mock_get_inv.assert_called_once()
        exported_ids = mock_get_inv.call_args.args[0]
        self.assertIn(normal_perception.id, exported_ids)
        self.assertNotIn(internal_perception.id, exported_ids)

    def test_create_files_raises_when_only_internal_voucher_perception(self):
        internal_invoice = self._create_invoice(
            self.internal_voucher_journal, move_type='out_refund'
        )
        internal_invoice.action_post()
        self._create_perception(internal_invoice, self.arciba_tax)

        wizard = self._create_wizard()
        with self.assertRaises(ValidationError):
            wizard.create_files()
