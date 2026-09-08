from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCheckbookCrossedDefault(TransactionCase):
    """Checkbook 'Crossed by Default' toggle.

    Uses a plain TransactionCase instead of AccountTestInvoicingCommon on
    purpose: see ivess_check_next_number/tests/test_account_payment_order.py
    for why (AFIP padron webservice call on res.partner creation).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        expense_account = cls.env["account.account"].search(
            [("account_type", "=", "expense")], limit=1
        )
        cls.check_journal = cls.env["account.journal"].create(
            {
                "name": "Crossed Default Test Journal",
                "type": "bank",
                "code": "CRSD1",
                "company_id": cls.company.id,
                "default_account_id": expense_account.id,
            }
        )

    def _create_checkbook(self, number, crossed_by_default=False):
        wizard = self.env["create.checkbook.wizard"].create(
            {
                "number": number,
                "journal_id": self.check_journal.id,
                "checkbook_format": "physical",
                "type": "common",
                "required_num": True,
                "start_num": "00000001",
                "end_num": "00000003",
                "crossed_by_default": crossed_by_default,
            }
        )
        wizard.create_checkbook()
        return self.env["account.payment.method.line"].search(
            [
                ("journal_id", "=", self.check_journal.id),
                ("number", "=", int(number)),
            ],
            limit=1,
        )

    def test_checkbook_created_with_flag_crosses_generated_checks(self):
        checkbook = self._create_checkbook("1", crossed_by_default=True)

        checks = self.env["account.check"].search([("checkbook_id", "=", checkbook.id)])
        self.assertTrue(checks)
        self.assertTrue(all(checks.mapped("crossed")))

    def test_checkbook_without_flag_does_not_cross_generated_checks(self):
        checkbook = self._create_checkbook("2", crossed_by_default=False)

        checks = self.env["account.check"].search([("checkbook_id", "=", checkbook.id)])
        self.assertTrue(checks)
        self.assertFalse(any(checks.mapped("crossed")))

    def test_toggling_flag_on_existing_checkbook_crosses_its_checks(self):
        checkbook = self._create_checkbook("3", crossed_by_default=False)
        checks = self.env["account.check"].search([("checkbook_id", "=", checkbook.id)])
        self.assertFalse(any(checks.mapped("crossed")))

        checkbook.write({"crossed_by_default": True})

        checks.invalidate_recordset(["crossed"])
        self.assertTrue(all(checks.mapped("crossed")))

    def test_untoggling_flag_uncrosses_its_checks(self):
        checkbook = self._create_checkbook("6", crossed_by_default=True)
        checks = self.env["account.check"].search([("checkbook_id", "=", checkbook.id)])
        self.assertTrue(all(checks.mapped("crossed")))

        checkbook.write({"crossed_by_default": False})

        checks.invalidate_recordset(["crossed"])
        self.assertFalse(any(checks.mapped("crossed")))

    def test_new_check_after_flag_enabled_defaults_to_crossed(self):
        checkbook = self._create_checkbook("4", crossed_by_default=True)

        new_check = self.env["account.check"].create(
            {
                "number": "00000099",
                "journal_id": self.check_journal.id,
                "checkbook_id": checkbook.id,
                "checkbook_format": "physical",
                "internal_type": "issued",
                "issued_check_state": "draft",
            }
        )
        self.assertTrue(new_check.crossed)

    def test_explicit_crossed_value_is_respected(self):
        checkbook = self._create_checkbook("5", crossed_by_default=True)

        new_check = self.env["account.check"].create(
            {
                "number": "00000098",
                "journal_id": self.check_journal.id,
                "checkbook_id": checkbook.id,
                "checkbook_format": "physical",
                "internal_type": "issued",
                "issued_check_state": "draft",
                "crossed": False,
            }
        )
        self.assertFalse(new_check.crossed)

    def test_issued_check_line_onchange_follows_checkbook_default(self):
        checkbook = self._create_checkbook("7", crossed_by_default=True)

        line_form = Form(self.env["account.payment.order.issued.check.line"])
        line_form.checkbook_id = checkbook

        self.assertTrue(line_form.crossed)

    def test_issued_check_line_onchange_follows_individual_check(self):
        checkbook = self._create_checkbook("8", crossed_by_default=False)
        check = self.env["account.check"].search(
            [("checkbook_id", "=", checkbook.id), ("number", "=", "00000001")]
        )
        check.crossed = True

        line_form = Form(self.env["account.payment.order.issued.check.line"])
        line_form.checkbook_id = checkbook
        line_form.issued_check_id = check

        self.assertTrue(line_form.crossed)
