{
    "name": "Ivess Invoice Import",
    "version": "19.0.0.0.0",
    "summary": "Importador de facturas de clientes desde archivo Excel (formato 'aguas')",
    "description": """
        Wizard de 3 pasos (subir archivo / previsualizar / confirmar) que
        importa facturas de cliente a account.move a partir de un archivo
        Excel desnormalizado (una fila por ítem facturado), agrupando por
        tipo de comprobante + letra + punto de venta + número. Son facturas
        de tipo fiscal interna: no generan CAE ni se envían a ARCA.

        No agrega campos nuevos a los modelos: matchea cliente por
        res.partner.vat (contra la columna "documento" del Excel) y producto
        por product.product.default_code (contra "cod art"), y deduplica
        contra account.move.ref.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": ["account", "l10n_ar_eynes"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/invoice_import_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
