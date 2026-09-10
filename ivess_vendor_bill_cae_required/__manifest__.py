{
    "name": "Ivess Vendor Bill CAE Required",
    "version": "19.0.0.0.0",
    "summary": "Exige CAE y vencimiento de CAE en facturas de proveedor, por compañía",
    "description": """
        Agrega una configuración por compañía ("Exigir CAE en facturas de
        proveedor") que, cuando está activa, vuelve obligatorios los campos
        CAE y Vencimiento de CAE en facturas y notas de crédito de
        proveedor (l10n_ar_eynes).

        Pensado para compañías tipo A (hoy 2, con vocación de sumar más),
        sin necesidad de tocar código cuando se agregue una nueva: alcanza
        con tildar la opción en la configuración de esa compañía.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/account_move_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
