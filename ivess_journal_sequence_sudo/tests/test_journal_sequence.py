from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestJournalSequenceSudo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Usuario contable SIN base.group_system (no puede crear ir.sequence)
        cls.user = cls.env["res.users"].create(
            {
                "name": "Contable sin admin",
                "login": "contable_sin_admin",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("account.group_account_manager").id,
                        ],
                    )
                ],
            }
        )
        cls.env = cls.env(user=cls.user)

    def _vals(self, journal_type, code):
        return {
            "name": "Test %s" % journal_type,
            "code": code,
            "type": journal_type,
        }

    def test_user_cannot_create_sequences_directly(self):
        """Precondición: el usuario de prueba realmente no puede crear secuencias."""
        self.assertFalse(self.env.user.has_group("base.group_system"))
        with self.assertRaises(AccessError):
            self.env["ir.sequence"].create({"name": "x"})

    def test_create_sale_journal_creates_sequences(self):
        """Un diario de venta se crea y trae sus 3 secuencias (normal, NC, ND)."""
        journal = self.env["account.journal"].create(self._vals("sale", "0099"))
        self.assertTrue(journal.sequence_id)
        self.assertTrue(journal.cn_sequence_id)
        self.assertTrue(journal.dn_sequence_id)
        self.assertTrue(journal.sequence_id.prefix.startswith("99-"))

    def test_create_other_types(self):
        """Los demás tipos que generan secuencia también se crean sin error."""
        for code, journal_type in (("0098", "payment"), ("0097", "receipt")):
            journal = self.env["account.journal"].create(
                self._vals(journal_type, code)
            )
            self.assertTrue(journal.sequence_id, journal_type)

    def test_sequence_permissions_not_widened(self):
        """El fix no amplía permisos: el usuario sigue sin poder escribir secuencias."""
        journal = self.env["account.journal"].create(self._vals("sale", "0096"))
        with self.assertRaises(AccessError):
            journal.sequence_id.write({"padding": 3})
