"""Reparación de traducciones es_AR de account_financial_report.

El es_AR.po de account_financial_report (OCA) trae 34 traducciones con la
codificación rota ("Compa????a", "D??bito") y cuatro sin tilde ("Periodo").
Odoo no pisa traducciones ya cargadas al actualizar un módulo, así que se
corrigen directamente en la base (campos, ayudas, valores de selección, modelos
y vistas) y, para los textos que salen del código (Excel), con fix_text.
"""
import re

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
    "comprobaci??n": "comprobación",
    "coincidir??n": "coincidirán",
    "cr??dito": "crédito",
    "d??bito": "débito",
    "espec??fico": "específico",
    "est??": "está",
    "l??neas": "líneas",
    "mostrar??n": "mostrarán",
    "mostrar??": "mostrará",
    "opci??n": "opción",
    "per??odo": "período",
    "trav??s": "través",
    "utilizar??": "utilizará",
}
# Se reemplaza primero el texto más largo ("mostrar??n" antes que "mostrar??").
_ORDERED_TOKENS = sorted(BROKEN_TOKENS.items(), key=lambda kv: -len(kv[0]))

# (tabla, columna jsonb traducible)
TRANSLATED_COLUMNS = [
    ("ir_model_fields", "field_description"),
    ("ir_model_fields", "help"),
    ("ir_model_fields_selection", "name"),
    ("ir_model", "name"),
    ("ir_ui_view", "arch_db"),
]


# Palabras sin tilde en la traducción es_AR de OCA ("Periodo", "Filtro periodo").
UNACCENTED_WORDS = {"Periodos": "Períodos", "Periodo": "Período", "periodos": "períodos", "periodo": "período"}
_UNACCENTED_RE = re.compile(r"\b(%s)\b" % "|".join(UNACCENTED_WORDS))


def fix_text(text):
    """Corrige un texto es_AR con la codificación rota o sin tilde."""
    if not text:
        return text
    if "??" in text:
        for broken, fixed in _ORDERED_TOKENS:
            text = text.replace(broken, fixed)
    return _UNACCENTED_RE.sub(lambda m: UNACCENTED_WORDS[m.group(1)], text)


def repair_es_ar_translations(cr):
    """Reemplaza en la base los textos es_AR rotos. Idempotente."""
    cr.execute("SELECT 1 FROM res_lang WHERE code = 'es_AR' AND active")
    if not cr.fetchone():
        return
    for table, column in TRANSLATED_COLUMNS:
        for broken, fixed in _ORDERED_TOKENS:
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

    # Palabras sin tilde, solo en los wizards y reportes de account_financial_report.
    scopes = [
        ("ir_model_fields", "field_description", "model LIKE '%%report.wizard'"),
        ("ir_ui_view", "arch_db", "key LIKE 'account_financial_report.%%'"),
    ]
    for table, column, scope in scopes:
        for word, fixed in UNACCENTED_WORDS.items():
            cr.execute(
                f"""
                UPDATE {table}
                   SET {column} = jsonb_set(
                       {column}, '{{es_AR}}',
                       to_jsonb(regexp_replace({column}->>'es_AR', %s, %s, 'g')))
                 WHERE {scope}
                   AND {column} ? 'es_AR'
                   AND {column}->>'es_AR' ~ %s
                """,  # noqa: S608 - tabla, columna y filtro son constantes de este módulo
                (r"\m%s\M" % word, fixed, r"\m%s\M" % word),
            )
