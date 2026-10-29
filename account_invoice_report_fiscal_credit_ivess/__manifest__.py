# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

{
    "name": "Account Invoice Report Fiscal Credit Ivess",
    "version": "19.0.0.0.1",
    "author": "Eynes SRL",
    "website": "http://www.eynes.com.ar",
    "category": "Accounting/Accounting",
    "summary": "Agrega el campo Crédito Fiscal al reporte Análisis de facturas",
    "description": """
        Agrega el campo "Crédito Fiscal" (fiscal_credit) al reporte
        "Análisis de facturas" (account.invoice.report). El valor se toma de
        las líneas de factura (account.move.line.fiscal_credit, definido en
        l10n_ar_eynes), por lo que solo lo tienen las líneas de facturas de
        proveedor: en el resto queda vacío.

        Se puede usar para filtrar y agrupar (junto a "Rubro Crédito Fiscal"
        e "IVA Compras") y como columna en la vista lista.
    """,
    "depends": [
        "account",
        "l10n_ar_eynes",
        "logistic_custom_ivess",
    ],
    "data": [
        "views/account_invoice_report.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
