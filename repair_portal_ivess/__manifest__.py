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
        - Procesar equipos por lote (hidrolavadora / pintura): agrupar equipos
          en un lote persistente (repair.batch), validar que compartan la misma
          etapa, y registrar el inicio/fin de etapa de todo el lote a la vez.
          El lote queda guardado hasta que se finaliza la etapa que lo conformó.
    """,
    'depends': [
        'portal',
        'quality_control_custom',
    ],
    'data': [
        'security/security.xml',
        'views/repair_portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'repair_portal_ivess/static/src/js/portal_barcode_scanner.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
