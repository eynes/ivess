{
    "name": "Ivess Report Menu Names",
    "version": "19.0.1.0.0",
    "summary": "Renombra los reportes de IVA del menú Contabilidad > Reportes > Impuestos",
    "description": """
        Cambia los nombres de los menús de los reportes de IVA de l10n_ar_eynes
        sin modificar la localización, para que no se pierdan al actualizar.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/menuitems.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
