# -*- coding: utf-8 -*-
{
    "name": "Ivess Partner Custom",
    "version": "19.0.0.0.25",
    "description": "",
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "base_address_extended",
        "sale",
        "account",
        "mail",
        "l10n_ar_eynes",
        "logistic_custom_ivess",
    ],
    "data": [
        "data/res_groups.xml",
        "data/mail_activity_type.xml",
        "security/ir.model.access.csv",
        "views/baja_madre_views.xml",
        "views/desvincular_hija_views.xml",
        "views/traspaso_saldo_views.xml",
        "views/visita_fuera_ruta_views.xml",
        "views/res_partner.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ivess_partner_custom/static/src/visitas_deuda/*",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
