{
    "name": "Ivess Checkbook Crossed Default",
    "version": "19.0.0.0.1",
    "summary": "Marca los cheques de una chequera como cruzados por defecto",
    "description": """
Agrega un booleano "Crossed by Default" a la chequera (account.payment.method.line).

Al activarlo:

* Marca como cruzados (crossed=True) todos los cheques ya existentes
  de esa chequera.
* Hace que los cheques que se generen de ahí en adelante en esa
  chequera nazcan con crossed=True por defecto.

Al desactivarlo, revierte: desmarca (crossed=False) todos los cheques
ya existentes de esa chequera, y deja de aplicarse el default a los
cheques nuevos.
""",
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/checkbook_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
