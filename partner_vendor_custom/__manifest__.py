# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    'name': 'Partner Vendor Custom',
    'version': '19.0.1.0.0',
    'summary': 'Validación de proveedores: CBU/CVU, email obligatorio y restricción de posición fiscal',
    'author': 'Eynes',
    'category': 'Contacts',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'purchase',
    ],
    'data': [
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
