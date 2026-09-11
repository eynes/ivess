{
    "name": "Import Partners",
    "version": "19.0.1.0.0",
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "l10n_ar_eynes",
        "logistic_custom_ivess",
        "ivess_partner_custom",
        "pricelist_custom",
    ],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/res_partner_import_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
