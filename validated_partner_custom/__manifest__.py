# -*- coding: utf-8 -*-
{
    'name': "Validated Partner Custom",
    'version': '19.0.0.0.0',
    'description': """
    """,
    'author': "Eynes",
    'category': 'Uncategorized',
    'depends': [
        'base',
        'account',
        'purchase',
    ],

    'data': [
        'security/res_groups.xml',
        'views/res_partner.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
