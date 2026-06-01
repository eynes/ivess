# -*- coding: utf-8 -*-
{
    'name': 'Aguas FC Integration',
    'version': '19.0.0.0.0',
    'author': 'Eynes',
    'category': 'Inventory',
    'summary': 'Integración Odoo ↔ Aguas para equipos de frío-calor',
    'depends': [
        'stock',
        'quality_control_custom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_company_views.xml',
        'views/stock_location_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
