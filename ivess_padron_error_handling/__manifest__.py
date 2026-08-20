# -*- coding: utf-8 -*-
{
    "name": "Ivess Padron Error Handling",
    "version": "19.0.0.0.1",
    "description": (
        "Allows saving a partner even if fetching perception/retention "
        "values from the Padron WS fails, reporting the error on the "
        "partner instead of blocking the save."
    ),
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "l10n_ar_padron_ws_consumer",
    ],
    "data": [
        "views/res_partner_view.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
