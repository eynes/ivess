from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestIssuedCheckNextNumber(TransactionCase):
    """Checkbook -> Check autocomplete on the payment order issued check line.

    Uses a plain TransactionCase instead of AccountTestInvoicingCommon on
    purpose: that common base creates a company-independent user/partner
    during setUpClass, and in this codebase that currently crashes
    (l10n_ar_padron_ws_consumer's res.partner create hook calls out to the
    AFIP padron webservice unconditionally on every res.partner creation).
    For the same reason this test reuses an existing partner instead of
    creating a new one.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.partner = cls.env['res.partner'].search(
            [('company_id', 'in', [cls.company.id, False])], limit=1
        )
        expense_account = cls.env['account.account'].search(
            [('account_type', '=', 'expense')], limit=1
        )

        cls.check_journal = cls.env['account.journal'].create(
            {
                'name': 'Check Next Number Test Journal',
                'type': 'bank',
                'code': 'CHKN1',
                'company_id': cls.company.id,
                'default_account_id': expense_account.id,
            }
        )

        wizard = cls.env['create.checkbook.wizard'].create(
            {
                'number': '1',
                'journal_id': cls.check_journal.id,
                'checkbook_format': 'physical',
                'type': 'common',
                'required_num': True,
                'start_num': '00000001',
                'end_num': '00000005',
            }
        )
        wizard.create_checkbook()

        cls.checkbook = cls.env['account.payment.method.line'].search(
            [
                ('journal_id', '=', cls.check_journal.id),
                ('number', '=', 1),
            ],
            limit=1,
        )

        cls.payment_journal = cls.env['account.journal'].create(
            {
                'name': 'Payment Next Number Test Journal',
                'type': 'payment',
                'code': 'PAYN2',
                'company_id': cls.company.id,
                'default_account_id': expense_account.id,
            }
        )

        cls.order = cls.env['account.payment.order'].create(
            {
                'partner_id': cls.partner.id,
                'journal_id': cls.payment_journal.id,
                'type': 'payment',
                'company_id': cls.company.id,
                'date': fields.Date.today(),
            }
        )

    def _get_check(self, number):
        return self.env['account.check'].search(
            [
                ('checkbook_id', '=', self.checkbook.id),
                ('number', '=', number),
            ],
            limit=1,
        )

    def _new_check_line_form(self):
        # A Form() opened directly on the payment order (as the real
        # "Agregar una linea" dialog does) would be more faithful, but
        # account.payment.order overrides get_views(self, views,
        # options=None) and dereferences `options.get(...)` unconditionally
        # (l10n_ar_eynes/models/account_payment_order.py), which crashes
        # when Form() calls get_views() without an options dict. That is a
        # pre-existing bug in l10n_ar_eynes unrelated to this module, so
        # the line model is exercised directly instead.
        return Form(self.env['account.payment.order.issued.check.line'])

    def test_autocomplete_lowest_available_number(self):
        line_form = self._new_check_line_form()
        line_form.payment_order_id = self.order
        line_form.journal_id = self.check_journal
        line_form.checkbook_id = self.checkbook
        line_form.amount = 100.0
        line = line_form.save()

        self.assertEqual(line.issued_check_id.number, '00000001')

    def test_manual_override_is_respected(self):
        check_3 = self._get_check('00000003')

        line_form = self._new_check_line_form()
        line_form.payment_order_id = self.order
        line_form.journal_id = self.check_journal
        line_form.checkbook_id = self.checkbook
        line_form.issued_check_id = check_3
        line_form.amount = 100.0
        line = line_form.save()

        self.assertEqual(line.issued_check_id, check_3)

    def test_sibling_lines_do_not_repeat_number(self):
        line1_form = self._new_check_line_form()
        line1_form.payment_order_id = self.order
        line1_form.journal_id = self.check_journal
        line1_form.checkbook_id = self.checkbook
        line1_form.amount = 50.0
        line1 = line1_form.save()

        line2_form = self._new_check_line_form()
        line2_form.payment_order_id = self.order
        line2_form.journal_id = self.check_journal
        line2_form.checkbook_id = self.checkbook
        line2_form.amount = 75.0
        line2 = line2_form.save()

        numbers = [line1.issued_check_id.number, line2.issued_check_id.number]
        self.assertEqual(sorted(numbers), ['00000001', '00000002'])

    def test_duplicate_check_on_same_order_raises(self):
        check_1 = self._get_check('00000001')

        self.env['account.payment.order.issued.check.line'].create(
            {
                'payment_order_id': self.order.id,
                'journal_id': self.check_journal.id,
                'checkbook_id': self.checkbook.id,
                'issued_check_id': check_1.id,
                'amount': 10.0,
            }
        )
        with self.assertRaises(ValidationError):
            self.env['account.payment.order.issued.check.line'].create(
                {
                    'payment_order_id': self.order.id,
                    'journal_id': self.check_journal.id,
                    'checkbook_id': self.checkbook.id,
                    'issued_check_id': check_1.id,
                    'amount': 20.0,
                }
            )
