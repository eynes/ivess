# -*- coding: utf-8 -*-
{
    'name': 'Repair Portal - Ivess',
    'version': '19.0.0.0.0',
    'author': 'Eynes',
    'category': 'Manufacturing/Repairs',
    'summary': 'Portal de seguimiento de órdenes de reparación Frío/Calor',
    'description': """
        Provee una vista portal para usuarios con acceso web que permite:
        - Ver todas las órdenes de reparación de equipos Frío/Calor en una tabla.
        - Acceder al detalle de cada orden y visualizar la etapa actual.
        - Avanzar o revertir la etapa desde la vista portal.
    """,
    'depends': [
        'portal',
        'quality_control_custom',
    ],
    'data': [
        'views/repair_portal_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
