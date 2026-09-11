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
          (percepciones de IIBB/IVA, impuestos internos, columnas "cod
          impuesto interno" / "cod imp especiales*") se resuelven, cada uno
          por separado y por línea, contra el mapeo configurable en
          Contabilidad > Configuración > Códigos de impuesto especial
          (importación) y se cargan tal cual (base/monto del Excel) en
          account.move.perception_ids / internal_taxes_ids.

        - Cobros: importa cobros de cliente a account.payment.order (tipo
          "receipt"/Recibo de Cobranza, conciliados contra las facturas que
          cancelan) a partir de un archivo Excel desnormalizado (una fila
          por factura aplicada), agrupando por tipo de comprobante + letra +
          punto de venta + número del recibo. El diario del recibo
          (account.journal tipo "receipt") se resuelve automáticamente
          tomando el único diario de ese tipo configurado en la compañía
          (a diferencia de las facturas, un recibo no es un comprobante
          autorizado por AFIP: no hay un diario distinto por letra/punto
          de venta para desambiguar). El cliente se determina a
          través de la factura ya importada que cada línea cancela (no hay
          CUIT en este archivo), y se deduplica contra
          account.payment.order.reference. Los recibos anulados en origen
          no se importan (no generan asiento). El medio de pago real
          (líneas de payment_mode_line_ids) se resuelve por línea a partir
          de las columnas "medio de pago" + "caja", contra el mapeo
          configurable en Contabilidad > Configuración > Medios de pago
          (importación de cobros); dentro de un mismo recibo puede haber
          más de un medio de pago distinto (ej. parte efectivo, parte
          cheque), y se arma una línea de payment_mode_line_ids por cada
          diario resuelto, con el importe agrupado de las facturas
          aplicadas con ese medio de pago.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": ["account", "l10n_ar_eynes"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/account_tax_views.xml",
        "views/invoice_import_tax_code_views.xml",
        "views/payment_import_payment_method_code_views.xml",
        "wizard/invoice_import_wizard_views.xml",
        "wizard/payment_import_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
