# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

{
    "name": "L10n AR Fiscal Credit Ivess",
    "version": "19.0.0.0.1",
    "author": "Eynes SRL",
    "website": "http://www.eynes.com.ar",
    "category": "Accounting/Accounting",
    "summary": "Ajusta la obligatoriedad del crédito fiscal en líneas de factura",
    "description": """
        - En facturas de venta, el campo "Crédito Fiscal" (fiscal_credit) de
          las líneas de factura deja de ser obligatorio y se oculta de la vista.
        - En facturas de proveedores, el campo "Crédito Fiscal" deja de ser
          obligatorio únicamente cuando el IVA de la línea es "IVA Compras 0%".
        - El subdiario de IVA prorrateable (Taxes Subjournal with
          Apportionable VAT) suma como "Exento" las líneas cuyo IVA es
          Exento o de alícuota 0%, aunque no tengan "Crédito Fiscal"
          cargado (ver punto anterior).
    """,
    "depends": [
        "account",
        "l10n_ar_eynes",
    ],
    "data": [
        "views/account_move_views.xml",
        "views/report_subjournal_apportionable_vat.xml",
        # "views/payment_order_report_fix.xml",
        "views/retention_certificate_report_fix.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
