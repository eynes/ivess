{
    "name": "Ivess Webservice",
    "version": "19.0.0.0.0",
    "summary": "Integración con el middleware de Ivess vía JSON-2 API",
    "description": """
        Expone los servicios consumidos por el middleware de Ivess
        mediante métodos @api.model llamados a través de la External
        JSON-2 API de Odoo, y centraliza la notificación Odoo → middleware
        en los flujos bidireccionales.
    """,
    "author": "Eynes",
    "category": "Tools",
    "depends": [
        "base",
        "l10n_ar_eynes",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
