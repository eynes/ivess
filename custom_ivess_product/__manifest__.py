# -*- coding: utf-8 -*-
{
    'name': "Custom Ivess Product",
    'version': '19.0.0.0.0',
    'description': """
    """,
    'author': "Eynes",
    'category': 'Product',
    'depends': [
        'base',
        'product',
        'stock',
        'sale_stock',
        'stock_request'
    ],

    'data': [
        'views/product_category.xml',
        'views/product_template.xml',
        'views/template_delivery_route.xml',
        'views/res_users.xml',
        'views/res_partner.xml',
        'views/delivery_route_number.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
