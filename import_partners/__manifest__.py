{
    "name": "Import Partners",
    "version": "19.0.2.0.0",
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "l10n_ar_eynes",
        "logistic_custom_ivess",
        "ivess_partner_custom",
        "pricelist_custom",
        "ivess_padron_error_handling",
    ],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/res_partner_import_wizard_views.xml",
        "wizard/res_partner_csv_upload_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
