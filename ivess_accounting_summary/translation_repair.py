"""Reparación de traducciones es_AR rotas de account_financial_report.

El es_AR.po de account_financial_report (OCA) trae 28 traducciones con la
codificación rota ("Compa????a", "D??bito"). Odoo no pisa traducciones ya
cargadas al actualizar un módulo, así que se corrigen directamente en la base
(campos, valores de selección, modelos y vistas) y, para los textos que salen
del código (Excel), con fix_text.
"""

BROKEN_TOKENS = {
    "Compa????a": "Compañía",
    "C??digo": "Código",
    "centralizaci??n": "centralización",
    "Anal??tica": "Analítica",
    "anal??ticas": "analíticas",
    "Cr??dito": "Crédito",
    "D??bito": "Débito",
    "Descripci??n": "Descripción",
    "N??mero": "Número",
    "Jerarqu??a": "Jerarquía",
    "jerarqu??a": "jerarquía",
    "??ltima": "Última",
    "modificaci??n": "modificación",
    "actualizaci??n": "actualización",
    "l??mite": "límite",
    "S??lo": "Sólo",
    "Acci??n": "Acción",
    "Autom??tica": "Automática",
    "Comprobaci??n": "Comprobación",
}

# (tabla, columna jsonb traducible)
TRANSLATED_COLUMNS = [
    ("ir_model_fields", "field_description"),
    ("ir_model_fields_selection", "name"),
    ("ir_model", "name"),
    ("ir_ui_view", "arch_db"),
]


def fix_text(text):
    """Corrige un texto es_AR con la codificación rota."""
    if not text or "??" not in text:
        return text
    for broken, fixed in BROKEN_TOKENS.items():
        text = text.replace(broken, fixed)
    return text


def repair_es_ar_translations(cr):
    """Reemplaza en la base los textos es_AR rotos. Idempotente."""
    cr.execute("SELECT 1 FROM res_lang WHERE code = 'es_AR' AND active")
    if not cr.fetchone():
        return
    for table, column in TRANSLATED_COLUMNS:
        for broken, fixed in BROKEN_TOKENS.items():
            cr.execute(
                f"""
                UPDATE {table}
                   SET {column} = jsonb_set(
                       {column}, '{{es_AR}}',
                       to_jsonb(replace({column}->>'es_AR', %s, %s)))
                 WHERE {column} ? 'es_AR'
                   AND {column}->>'es_AR' LIKE %s
                """,  # noqa: S608 - tabla y columna son constantes de este módulo
                (broken, fixed, f"%{broken}%"),
            )
