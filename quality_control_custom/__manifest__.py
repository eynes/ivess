# -*- coding: utf-8 -*-
{
    'name': 'Quality Control Custom',
    'version': '19.0.0.0.0',
    'author': 'Eynes',
    'category': 'Manufacturing/Quality',
    'summary': 'Extensiones de Control de Calidad y Reparaciones',
    'description': """
        Extiende las funcionalidades nativas de Control de Calidad y Reparaciones.
        - Creación automática de órdenes de reparación ante fallos de calidad.
        - Tipificación de productos para enrutamiento de flujos de reparación.
        - Pipeline secuencial para equipos de tipo Frío/Calor.
    """,
    'depends': [
        'base',
        'repair',
        'quality_control',
        'quality_repair',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/repair_order_revert_stage_wizard_views.xml',
        'views/stock_picking_type_views.xml',
        'views/product_template_views.xml',
        'views/quality_check_views.xml',
        'views/repair_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
