{
    "name": "Ivess Check Next Number",
    "version": "19.0.0.0.1",
    "summary": "Autocompleta el próximo número de cheque disponible al elegir la chequera",
    "description": """
        En el wizard "Crear Cheques propios" (emisión desde Orden de Pago),
        al seleccionar la Chequera el campo Cheque se autocompleta con el
        próximo número disponible (el más bajo libre) de esa chequera, en
        vez de exigir la búsqueda manual en el desplegable. El usuario
        puede seguir cambiándolo manualmente por excepción (cheque
        salteado, anulado, o fuera de orden).
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/perception_tax_line_view.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
