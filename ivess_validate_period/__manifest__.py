{
    "name": "Ivess Validate Period",
    "version": "19.0.0.0.0",
    "summary": "Auto-corrige la fecha contable según el cierre de período del diario",
    "description": """
        Antes de postear un asiento, valida que su fecha contable no sea
        anterior a la fecha de cierre del diario (l10n_ar_eynes). Si lo es,
        corrige la fecha al día siguiente al cierre, propaga el ajuste a la
        orden de pago relacionada si corresponde, y avisa al usuario para
        que reintente la validación.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
