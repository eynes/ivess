# -*- coding: utf-8 -*-
{
    "name": "Ivess Partner Custom",
    "version": "19.0.0.0.10",
    "description": "",
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "base_address_extended",
        "sale",
        "account",
        "l10n_ar_eynes",
        "logistic_custom_ivess",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/traspaso_saldo_views.xml",
        "views/visita_fuera_ruta_views.xml",
        "views/res_partner.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
