{
    "name": "Account Payment Order Other Payment Journal",
    "version": "19.0.0.0.1",
    "summary": "Diario por defecto configurable para Otros Pagos",
    "description": """
Agrega un campo de configuración por compañía para elegir el diario que se
propone por defecto al crear un registro desde el menú "Otros Pagos"
(account.payment.order con other_payment=True y type=payment).

Si no se configura, se mantiene el comportamiento actual (se propone el
primer diario de tipo Payment de la compañía).
""",
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
