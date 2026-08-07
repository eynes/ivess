# -*- coding: utf-8 -*-
{
    'name': 'Repair - Servicio Técnico F/C (POC)',
    'version': '19.0.1.0.0',
    'author': 'Eynes',
    'category': 'Manufacturing/Repair',
    'summary': 'POC: repair.order nativo para servicio técnico F/C originado en una venta',
    'description': """
        Módulo de prueba (NO productivo) para validar si se puede usar el flujo
        nativo de repair.order (equipo, N° de serie, piezas utilizadas, estados)
        para órdenes de reparación de servicio técnico que se originan desde una
        orden de venta, y que convive con quality_control_custom SIN modificarlo.

        - No toca ningún archivo de quality_control_custom.
        - Agrega una vista propia (mayor prioridad) que ajusta el formulario
          nativo únicamente para las órdenes vinculadas a una venta
          (sale_order_id seteado): muestra la pestaña nativa "Parts" y oculta
          los botones/campos específicos del pipeline Frío/Calor de taller.
        - Neutraliza el bloqueo de cierre ("Debe iniciar la etapa actual...")
          que impone quality_control_custom para equipos Frío/Calor, llamando
          a su método público existente (action_start_current_stage), sin
          reescribir ni saltear su lógica.
        - Incluye una acción de un clic para generar un caso de prueba
          completo (producto F/C, N° de serie, venta confirmada y la orden de
          reparación resultante en borrador, lista para recorrer a mano).
    """,
    'depends': ['repair', 'quality_control_custom', 'sale'],
    'data': [
        'views/repair_order_views.xml',
        'views/repair_order_actions.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
