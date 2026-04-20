Technical Design Specification: quality_control_custom
Target Odoo Version: v19
Module Name: quality_control_custom
Dependencies: base, repair, quality_control, stock

1. Descripción General
Este módulo extiende las funcionalidades nativas de Control de Calidad y Reparaciones en Odoo. Implementa la creación automática de órdenes de reparación ante fallos de calidad, introduce una tipificación de productos para enrutamiento de flujos de reparación, y crea un pipeline secuencial, inmutable y condicional (incluyendo lógica de terciarización) exclusivamente para equipos de tipo "Frío/Calor".

2. Modificaciones a Modelos Existentes (Inherit)
2.1. Modelo: product.template
Nuevos Campos:

repair_equipment_type (Selection):

Valores: [('frio_calor', 'Frío/Calor'), ('cafetera', 'Máquina de café/Cafetera')]

Atributos: string="Tipo de equipo para reparación", required=False.

Lógica: Si es False o cafetera, el producto seguirá el flujo estándar de Odoo. Si es frio_calor, activará el flujo customizado en repair.order.

2.2. Modelo: quality.check
Nuevos Campos:

auto_repair_id (Many2one): Relación con repair.order. Atributo readonly=True, copy=False.

Lógica de Negocio (Python):

Override del método de fallo: Interceptar la acción de registrar un control como fallido (típicamente do_fail() o la escritura del estado control_status == 'fail').

Condición: Verificar si el picking_id.picking_type_id.name o point_id.picking_type_id (dependiendo de la configuración del Tipo de Operación) corresponde a "Frío-Calor: Reparaciones".

Acción: Si falla y cumple la condición, crear un registro en repair.order.

Valores a heredar: product_id (del check/move_line), lot_id (Nro de serie), name (Referencia del documento origen, ej. el picking_id.name o el nombre del check pasarlo al origin de la reparación).

Vincular el ID creado al campo auto_repair_id.

2.3. Modelo: repair.order
Nuevos Campos:

repair_equipment_type (Selection): Campo related='product_id.product_tmpl_id.repair_equipment_type', readonly=True. Útil para lógica de visibilidad en vistas (UI).

frio_calor_stage (Selection): Define las etapas rígidas.

Valores: [('hidrolavadora', 'Limpieza con hidrolavadora'), ('pileta', 'Lavado en pileta'), ('prueba', 'Prueba y sanitización'), ('secado', 'Secado'), ('pintura', 'Pintura'), ('armado', 'Armado')]

Default: hidrolavadora.

requires_painting (Boolean): string="Requiere pintura", default=False.

is_outsourced (Boolean): string="Terciarizado", default=False. Bloquea la edición del registro.

quality_check_id (Many2one): Relación inversa quality.check, string="Control de Calidad Origen".

Lógica de Negocio y Restricciones (Python):

Avanzar Etapa (Método Custom): Crear un método action_next_frio_calor_stage() para avanzar al siguiente estado basándose en la tupla estricta de orden.

Regla Secuencial: hidrolavadora -> pileta -> prueba -> secado -> (Si requires_painting es True: pintura) -> armado. Si requires_painting es False, de secado salta a armado.

Inmutabilidad de Etapas: No usar el widget statusbar clickeable (en la vista se debe configurar options="{'clickable': '0'}"). Odoo v19 permite restringir esto desde la vista. Restringir en el método write que si el usuario intenta modificar frio_calor_stage directamente, lance un UserError, a menos que venga del método de avance o del wizard de reversión.

Condición de Pintura: En el método write, si el usuario cambia requires_painting de True a False, y la orden está en etapa pintura, lanzar un ValidationError indicando que no se puede desmarcar si la etapa ya está en ejecución o superada.

Bloqueo por Terciarización: Sobrescribir write y unlink. Si is_outsourced == True, no permitir modificar ningún campo excepto los relacionados al desbloqueo (is_outsourced), lanzando UserError.

3. Nuevos Modelos
3.1. Wizard: repair.order.revert.stage.wizard
Propósito: Manejar el retroceso de etapas del flujo Frío/Calor.
Campos:

repair_id (Many2one): repair.order.

current_stage (Char/Selection): Solo lectura, muestra el estado actual.

target_stage (Selection): Las opciones deben cargarse dinámicamente (_compute_target_stage) mostrando solo las etapas lógicamente previas a la actual. Ejemplo: Si está en secado, mostrar solo hidrolavadora, pileta, prueba. Debe respetar si existía o no la etapa pintura.

Método:

action_revert_stage(): Cambia el frio_calor_stage de la repair.order al target_stage seleccionado y deja un mensaje en el chatter (message_post) indicando la regresión manual.

4. Modificaciones a la Interfaz de Usuario (Views)
4.1. Vista: product.template.form.inherit
Ubicación: Pestaña "Inventario" o "Ventas" (o crear un grupo "Reparaciones").

Elemento: Agregar el campo repair_equipment_type.

4.2. Vista: quality.check.form.inherit
Elemento: Agregar un Smart Button tipo statinfo en el div class="oe_button_box".

Visibilidad: Solo visible si auto_repair_id está seteado (invisible="not auto_repair_id").

Acción: Abrir la vista form de la orden de reparación vinculada.

4.3. Vista: repair.order.form.inherit
Bloqueo de UI (Terciarizar): Agregar un atributo readonly="is_outsourced" a todos los campos críticos usando la nueva sintaxis de atributos condicionales de Odoo (o envolviendo en un <field ... readonly="is_outsourced"/>).

Header (Botones):

Botón Avanzar Etapa: type="object", name="action_next_frio_calor_stage", invisible="repair_equipment_type != 'frio_calor' or frio_calor_stage == 'armado' or is_outsourced".

Botón Revertir etapa: Llama a la acción (Action Window) del wizard repair.order.revert.stage.wizard. invisible="repair_equipment_type != 'frio_calor' or frio_calor_stage == 'hidrolavadora' or is_outsourced".

Botón Terciarizar: type="object", name="action_outsource", invisible="is_outsourced".

Botón Recibir de tercero: type="object", name="action_receive_from_third_party", invisible="not is_outsourced".

Header (Statusbar):

Agregar <field name="frio_calor_stage" widget="statusbar" statusbar_visible="hidrolavadora,pileta,prueba,secado,pintura,armado" options="{'clickable': '0'}" invisible="repair_equipment_type != 'frio_calor'"/>

Nota para Claude: Asegurar que la etapa pintura se oculte dinámicamente del statusbar_visible si requires_painting es False (puede requerir jugar con dos statusbars condicionales con invisible="...", ya que el atributo statusbar_visible es estático en el XML).

Form (Nuevos campos):

Agregar requires_painting debajo de la información del producto. invisible="repair_equipment_type != 'frio_calor'".

Agregar is_outsourced como invisible="1".

Agregar repair_equipment_type como invisible="1".

5. Implementación de Lógica Botones (Python repair.order)
action_outsource(self):

Setear self.is_outsourced = True.

Dejar registro en el chatter.

action_receive_from_third_party(self):

Setear self.is_outsourced = False.

Retornar la orden a la primera etapa: self.frio_calor_stage = 'hidrolavadora'.

Dejar registro en el chatter.

6. Registro de Implementación

6.1. Estructura del módulo creado

quality_control_custom/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── product_template.py
│   ├── quality_check.py
│   └── repair_order.py
├── wizard/
│   ├── __init__.py
│   ├── repair_order_revert_stage_wizard.py
│   └── repair_order_revert_stage_wizard_views.xml
├── views/
│   ├── product_template_views.xml
│   ├── quality_check_views.xml
│   └── repair_order_views.xml
└── security/
    └── ir.model.access.csv

6.2. Detalle de implementación por punto

Punto 2.1 - product.template (product_template.py):
- Campo repair_equipment_type (Selection): valores 'frio_calor' y 'cafetera'. No requerido.
- Vista: se hereda product.product_template_form_view, se agrega grupo "Reparaciones" con el campo después de group_general.

Punto 2.2 - quality.check (quality_check.py):
- Campo auto_repair_id (Many2one → repair.order): readonly=True, copy=False.
- Override de do_fail(): al fallar, verifica si picking_id.picking_type_id.name == "Frío-Calor: Reparaciones" (o el primer picking_type del point_id como fallback). Si cumple, llama a _create_auto_repair_order().
- Método _create_auto_repair_order(): crea repair.order con product_id, lot_id (primer lote), quality_check_id. Deja message_post en ambos registros (check y repair).
- Método action_view_auto_repair(): abre la vista form de la reparación vinculada.
- Vista: se hereda quality_control.quality_check_view_form, se agrega Smart Button "Orden de Reparación" con icono fa-wrench en el button_box, visible solo si auto_repair_id está seteado.

Punto 2.3 - repair.order (repair_order.py):
- Campo repair_equipment_type (Selection related): related='product_id.product_tmpl_id.repair_equipment_type', readonly=True, store=True.
- Campo frio_calor_stage (Selection): 6 etapas (hidrolavadora, pileta, prueba, secado, pintura, armado). Default: 'hidrolavadora'. Con tracking=True.
- Campo requires_painting (Boolean): default=False.
- Campo is_outsourced (Boolean): default=False.
- Campo quality_check_id (Many2one → quality.check): readonly=True, copy=False.
- Método _get_stage_sequence(): retorna la lista de etapas según requires_painting (con o sin 'pintura').
- Método action_next_frio_calor_stage(): avanza secuencialmente. Valida tipo frio_calor, no terciarizado, no última etapa. Usa context '_frio_calor_stage_advance' para bypass del write. Deja message_post.
- Método action_outsource(): setea is_outsourced=True con context '_outsource_action'. Deja message_post.
- Método action_receive_from_third_party(): setea is_outsourced=False y frio_calor_stage='hidrolavadora'. Deja message_post.
- Override de write(): 3 validaciones:
  1. Bloqueo por terciarización: si is_outsourced y no viene del context '_outsource_action', solo permite campos de mensajería.
  2. Protección de frio_calor_stage: no permite escritura directa sin context '_frio_calor_stage_advance' o '_revert_stage'.
  3. Validación de requires_painting: no permite desmarcar si la etapa actual es 'pintura' o 'armado'.
- Override de unlink(): no permite eliminar órdenes terciariadas.

Punto 3.1 - Wizard repair.order.revert.stage.wizard (repair_order_revert_stage_wizard.py):
- Modelo TransientModel con _name='repair.order.revert.stage.wizard'.
- Campos: repair_id (Many2one), current_stage (Selection readonly), target_stage (Selection requerido).
- default_get(): carga repair_id y current_stage desde active_id del contexto.
- _onchange_current_stage(): filtra target_stage mostrando solo etapas previas a la actual (respeta requires_painting).
- action_revert_stage(): valida que target sea anterior, escribe con context '_revert_stage', deja message_post con detalle de regresión.
- Vista form en wizard/repair_order_revert_stage_wizard_views.xml con botones Revertir/Cancelar.
- Acción ir.actions.act_window (target=new) referenciada desde el botón "Revertir Etapa" en repair.order.

Punto 4.1 - Vista product.template:
- Hereda product.product_template_form_view.
- Agrega grupo "Reparaciones" con campo repair_equipment_type después de group_general vía xpath.

Punto 4.2 - Vista quality.check:
- Hereda quality_control.quality_check_view_form.
- Agrega Smart Button en div button_box con invisible="not auto_repair_id".

Punto 4.3 - Vista repair.order:
- Hereda repair.view_repair_order_form.
- Campos invisibles auxiliares (repair_equipment_type, is_outsourced, requires_painting, frio_calor_stage) inyectados después de unreserve_visible.
- 4 botones en header antes de action_validate: Avanzar Etapa, Revertir Etapa (acción wizard), Terciarizar, Recibir de tercero. Cada uno con sus condiciones de invisible.
- 2 statusbars condicionales después del statusbar de state: uno con pintura (invisible si no requires_painting) y otro sin pintura (invisible si requires_painting). Ambos con options="{'clickable': '0'}" y invisible si no es frio_calor.
- Campo requires_painting después de product_id, invisible si no es frio_calor, readonly si terciarizado.
- Campo quality_check_id en grupo derecho después de tag_ids, readonly, invisible si no está seteado.
- Atributos readonly="is_outsourced" agregados a campos críticos: product_id, partner_id, under_warranty, schedule_date, user_id, internal_notes.

Punto 5 - Botones (implementados en repair_order.py):
- action_outsource(): is_outsourced=True + chatter.
- action_receive_from_third_party(): is_outsourced=False, frio_calor_stage='hidrolavadora' + chatter.

Security:
- ir.model.access.csv: acceso CRUD al wizard repair.order.revert.stage.wizard para el grupo repair.group_repair_user.
