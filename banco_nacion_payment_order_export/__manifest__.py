# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "Banco Nación Payment Order Export",
    "version": "19.0.1.0.0",
    "summary": "Exportador de archivo CSV de transferencias masivas a "
    "proveedores para Banco Nación",
    "author": "Eynes",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "depends": [
        "l10n_ar_eynes",
        "partner_vendor_custom",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/account_payment_order_views.xml",
        "wizard/banco_nacion_payment_order_export_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
