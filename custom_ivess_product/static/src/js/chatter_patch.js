/** @odoo-module **/

import { Chatter } from "@mail/core/web/chatter";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

console.log(">>> EL ARCHIVO CHATTER_PATCH.JS SE ESTA LEYENDO BIEN <<<"); // Agrega esto

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        // Inyectamos los servicios para llamar a Python y abrir ventanas
        this.actionService = useService("action");
        this.orm = useService("orm");
        console.log("PRUEBA DENTRO DEL CHATTER");
    },

    // Interceptamos la nueva función de Odoo 19
    toggleComposer(composerType) {
        // Obtenemos el modelo y el ID de forma segura según la estructura de v19
        const threadModel = this.props.threadModel || (this.state && this.state.thread && this.state.thread.model);
        const threadId = this.props.threadId || (this.state && this.state.thread && this.state.thread.id);
        console.log("PRUEBA DENTRO DE TOGGLE");
        // 1. Verificamos que estén intentando abrir una "nota"
        // 2. Verificamos que sea tu modelo
        // 3. Verificamos que el registro esté guardado (tenga ID)
        if (composerType === 'note' && threadModel === 'stock.request.order' && threadId) {

            // Llamamos a nuestra función Python
            this.orm.call(
                'stock.request.order',
                'action_open_note_wizard',
                [[threadId]]
            ).then((actionDetails) => {
                // Abrimos el modal con la plantilla
                this.actionService.doAction(actionDetails);
            });

            // ¡IMPORTANTE! Retornamos vacío para cortar la ejecución nativa
            // Esto evita que se abra el cuadrito de abajo.
            return;
        }

        // Si es otro botón (como "Enviar mensaje") o estamos en otro modelo (Ventas, etc.),
        // dejamos que Odoo ejecute su código original sin interferir.
        return super.toggleComposer(...arguments);
    }
});
