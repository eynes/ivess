{
    "name": "Ivess Invoice Import",
    "version": "19.0.0.0.0",
    "summary": "Importador de facturas y cobros de clientes desde archivo Excel (formato 'aguas')",
    "description": """
        Wizards de 3 pasos (subir archivo / previsualizar / confirmar):

        - Facturas: importa facturas de cliente a account.move a partir de
          un archivo Excel desnormalizado (una fila por ítem facturado),
          agrupando por tipo de comprobante + letra + punto de venta +
          número. Son comprobantes que ya tienen CAE en el sistema origen
          (se importa tal cual, columna "cae", sin pedirlo a ARCA); Odoo las
          postea (action_post) y les asigna su propia numeración según el
          diario de ventas elegido en el wizard. Matchea cliente por
          res.partner.vat (contra la columna "documento" del Excel) y
          producto por product.product.default_code (contra "cod art"), y
          deduplica contra account.move.ref. Los impuestos especiales
          (percepciones de IIBB/IVA, impuestos internos, columna "cod
          impuesto especial") se resuelven contra el mapeo configurable en
          Contabilidad > Configuración > Códigos de impuesto especial
          (importación) y se cargan tal cual (base/monto del Excel) en
          account.move.perception_ids / internal_taxes_ids.

        - Cobros: importa cobros de cliente a account.payment (conciliados
          contra las facturas que cancelan) a partir de un archivo Excel
          desnormalizado (una fila por factura aplicada), agrupando por tipo
          de comprobante + letra + punto de venta + número del recibo. El
          cliente se determina a través de la factura ya importada que cada
          línea cancela (no hay CUIT en este archivo), y se deduplica contra
          account.payment.payment_reference. Los recibos anulados en origen
          no se importan (no generan asiento). "Medio de pago" y "caja" del
          archivo se muestran solo a título informativo.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": ["account", "l10n_ar_eynes"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/invoice_import_tax_code_views.xml",
        "wizard/invoice_import_wizard_views.xml",
        "wizard/payment_import_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
