{
    'name': "Pricelist Custom",
    'version': '19.0.1.0.0',
    'description': (
        "Lógica de precios personalizada: precios especiales por cliente, "
        "% de descuento y lista de precios por plantilla de ruta de reparto."
    ),
    'author': "Eynes",
    'category': 'Sale',
    'depends': [
        'sale',
        'product',
        'logistic_custom_ivess',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/template_delivery_route_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
