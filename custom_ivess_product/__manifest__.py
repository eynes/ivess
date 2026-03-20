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
        'mail',
        'product',
        'stock',
        'sale_stock',
        'stock_request'
    ],

    'data': [
        'data/paperformat.xml',
        'data/product_template_report.xml',
        'views/res_config_settings.xml',
        'views/stock_request_order.xml',
        'views/product_category.xml',
        'views/product_template.xml',
        'views/product_product.xml',
        'views/template_delivery_route.xml',
        'views/res_users.xml',
        'views/res_partner.xml',
        'views/delivery_route_number.xml',
        'views/mail_template.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_ivess_product/static/src/js/composer_patch.js',
        ],
    },
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
