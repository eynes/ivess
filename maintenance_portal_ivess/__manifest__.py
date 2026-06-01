# -*- coding: utf-8 -*-
{
    'name': 'Maintenance Portal - Ivess',
    'version': '19.0.0.0.0',
    'author': 'Eynes',
    'category': 'Maintenance',
    'summary': 'Vista portal para órdenes de mantenimiento',
    'description': """
        Provee una vista portal para usuarios con acceso web que permite:
        - Ver todas las órdenes de mantenimiento en una tabla paginada.
        - Acceder al detalle de cada solicitud de mantenimiento.
    """,
    'depends': [
        'portal',
        'maintenance',
        'helpdesk_maint_custom',
        'mrp_maintenance',
        'hr_maintenance',
    ],
    'data': [
        'views/maintenance_views.xml',
        'views/maintenance_portal_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
