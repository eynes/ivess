from odoo import SUPERUSER_ID, api

# La traducción es_AR de account_financial_report viene con la codificación
# rota ("Compa????a"). Odoo no pisa traducciones ya cargadas al actualizar un
# módulo, así que se corrigen acá los términos del wizard del libro diario.
FIELD_LABELS = {
    "company_id": "Compañía",
    "with_auto_sequence": "Mostrar secuencia automática",
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env["res.lang"].search([("code", "=", "es_AR")]):
        return
    for field_name, label in FIELD_LABELS.items():
        field = env["ir.model.fields"]._get("journal.ledger.report.wizard", field_name)
        if field:
            field.with_context(lang="es_AR").field_description = label
