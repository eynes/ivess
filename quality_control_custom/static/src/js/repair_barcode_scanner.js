/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useBus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class RepairBarcodeScanner extends Component {
    static template = "quality_control_custom.RepairBarcodeScanner";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        const barcodeService = useService("barcode");

        this.state = useState({
            lastScanned: "",
            status: "waiting",
        });

        useBus(barcodeService.bus, "barcode_scanned", (ev) => this.onBarcodeScanned(ev));
    }

    async onBarcodeScanned({ detail: { barcode } }) {
        this.state.lastScanned = barcode;
        this.state.status = "searching";

        try {
            const result = await this.orm.call("repair.order", "find_repair_by_serial", [barcode]);

            if (result.error) {
                this.state.status = "not_found";
                this.notification.add(result.message, { type: "warning" });
                return;
            }

            this.state.status = "found";
            await this.actionService.doAction(result);
        } catch {
            this.state.status = "not_found";
            this.notification.add(_t("Error al buscar la orden de reparación."), { type: "danger" });
        }
    }
}

registry.category("actions").add("repair_barcode_scanner", RepairBarcodeScanner);
