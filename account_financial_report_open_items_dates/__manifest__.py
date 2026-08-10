# -- coding: utf-8 --
##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
#
##############################################################################

{
    "name": "Account Financial Report - Open Items Document Date",
    "version": "19.0.0.0.1",
    "author": "Eynes SRL",
    "website": "http://www.eynes.com.ar",
    "category": "Accounting/Accounting",
    "summary": "Agrega la fecha comprobante junto a la fecha contable "
    "en el reporte de Partidas Abiertas",
    "description": """
        Extiende el reporte "Partidas Abiertas" (Open Items) de
        account_financial_report para distinguir, en los casos en que
        existan (facturas de proveedores, facturas de clientes), la
        fecha comprobante (invoice_date) de la fecha contable (date):

        - Wizard: agrega un filtro opcional por rango de fecha comprobante
          (desde / hasta).
        - Vista Odoo y PDF: agregan la columna "Fecha comprobante" junto a
          la columna "Fecha contable".
        - Excel: agrega la columna "Fecha comprobante" junto a la columna
          "Fecha contable" y el filtro aplicado.
    """,
    "depends": [
        "account_financial_report",
    ],
    "data": [
        "wizard/open_items_wizard_view.xml",
        "report/templates/open_items.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
