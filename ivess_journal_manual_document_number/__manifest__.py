{
    "name": "Ivess Journal Manual Document Number",
    "version": "19.0.0.0.0",
    "summary": "Permite forzar numeración manual en facturas de cliente, por diario",
    "description": """
        Agrega un booleano en el diario ("Forzar numeración manual") que,
        cuando está activo, hace que las facturas de cliente de ese diario
        se comporten como una factura de proveedor: el número se ingresa a
        mano y se omite el autocompletado con el prefijo y la secuencia del
        diario al validar.

        Pensado para diarios de venta que no siguen la numeración interna
        estándar (ej. Liquidación de Granos, donde el número lo define la
        contraparte), sin necesidad de tocar el tipo de diario ni "Usa
        Documentos" para lograrlo.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
