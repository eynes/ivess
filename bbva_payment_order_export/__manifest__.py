# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "BBVA Payment Order Export",
    "version": "19.0.2.0.0",
    "summary": "Exportador de archivo TXT posicional para el servicio Pago a "
    "Proveedores de BBVA/Banco Francés",
    "author": "Eynes",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "depends": [
        "l10n_ar_eynes",
        "partner_vendor_custom",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_views.xml",
        "wizard/bbva_payment_order_export_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
