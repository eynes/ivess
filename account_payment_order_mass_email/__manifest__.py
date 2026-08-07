{
    "name": "Account Payment Order Mass Email",
    "version": "19.0.0.0.0",
    "summary": "Envío masivo por email de órdenes de pago/recibo validadas",
    "description": """
        Permite seleccionar varias órdenes de pago/recibo desde la
        vista de lista de account.payment.order y enviarlas por email
        de forma masiva, notificando si alguna de las seleccionadas
        no está validada.
    """,
    "author": "Eynes",
    "website": "http://www.eynes.com.ar",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/account_payment_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
