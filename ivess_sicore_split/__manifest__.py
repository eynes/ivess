{
    "name": "Ivess SICORE Split",
    "version": "19.0.0.0.1",
    "summary": "Ajustes al reporte SICORE: separador decimal, archivos "
    "separados IVA/Ganancias y código AFIP configurable en la percepción",
    "description": """
        T16639.

        - El separador decimal de los montos pasa de coma a punto.
        - Las retenciones de IVA y de Ganancias se exportan en archivos
          separados (antes salían mezcladas en el mismo archivo).
        - Se agrega el campo "SICORE Tax Code" en la percepción
          (Contabilidad > Configuración > Impuestos), para no depender de
          buscar el código por el diario vinculado.
        - El campo "Código de retención AFIP" del diario solo se muestra
          para diarios de tipo Retentions/Perceptions.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/account_tax_views.xml",
        "views/account_journal_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
