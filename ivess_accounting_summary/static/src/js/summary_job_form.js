import {FormController} from "@web/views/form/form_controller";
import {formView} from "@web/views/form/form_view";
import {onMounted, onWillUnmount} from "@odoo/owl";
import {registry} from "@web/core/registry";

const FINAL_STATES = ["done", "error"];
const REFRESH_MS = 3000;

/**
 * Pantalla de progreso del Cierre Mensual en segundo plano: mientras el
 * trabajo no termina (ni falla) la ficha se vuelve a leer sola cada pocos
 * segundos, así la barra de avance, la etapa y los contadores se mueven sin
 * tener que recargar. Al terminar se lee una última vez y se detiene.
 */
export class SummaryJobFormController extends FormController {
    setup() {
        super.setup();
        onMounted(() => {
            this._refreshTimer = setInterval(() => this._refreshProgress(), REFRESH_MS);
        });
        onWillUnmount(() => clearInterval(this._refreshTimer));
    }

    async _refreshProgress() {
        const root = this.model.root;
        if (!root.resId || root.dirty || FINAL_STATES.includes(root.data.state)) {
            return;
        }
        await root.load();
    }
}

registry.category("views").add("ivess_summary_job_form", {
    ...formView,
    Controller: SummaryJobFormController,
});
