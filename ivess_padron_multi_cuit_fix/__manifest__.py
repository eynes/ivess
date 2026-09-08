# -*- coding: utf-8 -*-
{
    "name": "Ivess Padron Multi CUIT Fix",
    "version": "19.0.0.0.3",
    "description": (
        "Fixes l10n_ar_padron_ws_consumer so that: "
        "(1) a Padron update targets the partner(s) that actually "
        "requested it, instead of an unrelated partner that happens to "
        "share the same CUIT/VAT; "
        "(2) the perception/retention journal lookup is scoped to the "
        "active company and also recognizes the 'SALTD' jurisdiction code "
        "(same as 'SALT'), instead of raising 'Expected singleton' when "
        "the domain matches more than one journal at once."
    ),
    "author": "Eynes",
    "category": "Contacts",
    "depends": [
        "base",
        "l10n_ar_padron_ws_consumer",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
