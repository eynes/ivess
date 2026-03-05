# -*- coding: utf-8 -*-
{
    'name': "Sale Custom Ivess",
    'version': '19.0.0.0.0',
    'description': """
    """,
    'author': "Eynes",
    'category': 'Sale',
    'depends': [
        'base',
        'account',
        'sale',
        'fleet',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_route_number.xml',
        'views/res_partner.xml',
        'views/template_delivery_route.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
