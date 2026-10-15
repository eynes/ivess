# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "IVESS - Selector de empresa agrupadora",
    "version": "19.0.1.0.0",
    "summary": "Grupos de empresas en el selector y bloqueo de cambio por usuario",
    "category": "Hidden",
    "author": "Eynes",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/res_company_group_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "company_group_switcher/static/src/**/*",
        ],
    },
    "post_load": "post_load",
    "installable": True,
    "application": False,
    "auto_install": False,
}
