{
    "name": "Ivess Payment Line Description",
    "version": "19.0.1.0.0",
    "summary": "Wizard para editar la descripción de las líneas de pago de Otros Pagos",
    "description": """
        En el formulario de Otros Pagos, fuera de borrador las líneas del
        método de pago son de solo lectura. Agrega el botón "Editar
        descripción" que abre un wizard para modificar únicamente la
        descripción de cada línea, dejando registro del cambio en el
        chatter. No modifica los asientos ya generados.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/payment_line_description_wizard_views.xml",
        "views/account_payment_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
