/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    ProgressBarField,
    progressBarField,
} from "@web/views/fields/progress_bar/progress_bar_field";
import { onMounted, onWillUnmount } from "@odoo/owl";

const POLL_INTERVAL_MS = 2000;

/**
 * Barra de progreso de la importación de cobros: se recarga sola mientras la
 * importación corre en segundo plano y, cuando termina (o se interrumpe),
 * vuelve a la vista completa del wizard.
 */
export class ImportProgressBarField extends ProgressBarField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.polling = false;
        onMounted(() => {
            this.timer = setInterval(() => this.poll(), POLL_INTERVAL_MS);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async poll() {
        if (this.polling) {
            return;
        }
        this.polling = true;
        try {
            const { resModel, resId } = this.props.record;
            const [wizard] = await this.orm.read(resModel, [resId], [
                "state",
                "is_stalled",
            ]);
            if (wizard.state !== "processing" || wizard.is_stalled) {
                clearInterval(this.timer);
                await this.actionService.doActionButton({
                    type: "object",
                    name: "action_reopen",
                    resModel,
                    resId,
                    resIds: [resId],
                    context: {},
                    buttonContext: {},
                });
            } else {
                await this.props.record.load();
            }
        } finally {
            this.polling = false;
        }
    }
}

export const importProgressBarField = {
    ...progressBarField,
    component: ImportProgressBarField,
    displayName: "Barra de progreso de importación",
};

registry.category("fields").add("ivess_import_progressbar", importProgressBarField);
