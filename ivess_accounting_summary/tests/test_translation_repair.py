from odoo.tests import TransactionCase, tagged

from ..translation_repair import fix_text, repair_es_ar_translations


@tagged("post_install", "-at_install")
class TestTranslationRepair(TransactionCase):
    def test_fix_text(self):
        self.assertEqual(fix_text("D??bito"), "Débito")
        self.assertEqual(fix_text("Mostrar Secuencia Autom??tica"), "Mostrar Secuencia Automática")
        self.assertEqual(fix_text("Compa????a"), "Compañía")
        self.assertEqual(fix_text("Sin cambios"), "Sin cambios")

    def test_repair_fixes_wizard_field_labels(self):
        if not self.env["res.lang"].search([("code", "=", "es_AR")]):
            self.skipTest("es_AR no está instalado en esta base")
        field = self.env["ir.model.fields"]._get("general.ledger.report.wizard", "show_cost_center")
        field.with_context(lang="es_AR").field_description = "Mostrar Cuenta Anal??tica"
        field.flush_recordset()
        repair_es_ar_translations(self.env.cr)
        self.env.invalidate_all()
        self.assertEqual(
            field.with_context(lang="es_AR").field_description,
            "Mostrar Cuenta Analítica",
        )
