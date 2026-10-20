from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPaymentLineDescription(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env['account.journal'].create(
            {'name': 'Caja test', 'code': 'CJT', 'type': 'cash'}
        )
        cls.order = cls.env['account.payment.order'].create(
            {
                'company_id': cls.env.company.id,
                'payment_mode_line_ids': [
                    (
                        0,
                        0,
                        {
                            'payment_mode_id': cls.journal.id,
                            'name': 'Original',
                            'amount': 100.0,
                        },
                    )
                ],
            }
        )
        cls.line = cls.order.payment_mode_line_ids

    def _wizard(self):
        return self.env['payment.line.description.wizard'].create(
            {'payment_order_id': self.order.id}
        )

    def test_default_get_loads_payment_lines(self):
        values = self.env['payment.line.description.wizard'].with_context(
            default_payment_order_id=self.order.id
        ).default_get(['payment_order_id', 'line_ids'])
        self.assertEqual(len(values['line_ids']), 1)

    def test_apply_updates_description_and_logs(self):
        self.order.state = 'posted'
        wizard = self._wizard()
        wizard.write(
            {
                'line_ids': [
                    (0, 0, {'payment_line_id': self.line.id, 'name': 'Nueva'})
                ]
            }
        )
        wizard.action_apply()
        self.assertEqual(self.line.name, 'Nueva')
        self.assertIn('Original', self.order.message_ids[0].body)
        self.assertIn('Nueva', self.order.message_ids[0].body)
        self.assertNotIn('&lt;br', self.order.message_ids[0].body)

    def test_apply_in_draft_is_refused(self):
        wizard = self._wizard()
        with self.assertRaises(UserError):
            wizard.action_apply()
