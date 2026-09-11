{
    "name": "Account Payment Order Report Lines",
    "version": "19.0.1.0.0",
    "summary": "Agrega líneas del método de pago y otros conceptos al reporte de OP",
    "description": """
        Extiende el reporte l10n_ar_eynes.payment_order para mostrar el detalle
        de las líneas del método de pago (payment_mode_line_ids) con su moneda,
        y agrega una nueva sección de Otros Conceptos (concept_line_ids).
    """,
    "author": "Eynes",
    "website": "http://www.eynes.com.ar",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "report/payment_order_report.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
