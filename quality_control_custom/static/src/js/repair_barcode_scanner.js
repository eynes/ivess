/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useBus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";

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

        // Lector físico (USB/HID/Bluetooth)
        useBus(barcodeService.bus, "barcode_scanned", (ev) => this.onBarcodeScanned(ev));
    }

    async openCameraScanner() {
        this.state.status = "waiting";
        try {
            const barcode = await scanBarcode(this.env);
            if (barcode) {
                await this.processBarcode(barcode);
            }
        } catch (err) {
            const isPermission = err?.message?.toLowerCase().includes("permission") ||
                                 err?.message?.toLowerCase().includes("allowed") ||
                                 err?.message?.toLowerCase().includes("authorization");
            const isNotFound = err?.message?.toLowerCase().includes("no device");
            const isInsecure = !window.location.protocol.startsWith("https") &&
                               !["localhost", "127.0.0.1"].includes(window.location.hostname);

            if (isInsecure) {
                this.notification.add(
                    _t("La cámara requiere HTTPS. Acceda a Odoo con una conexión segura (https://)."),
                    { type: "danger", sticky: true }
                );
            } else if (isPermission) {
                this.notification.add(
                    _t("Permiso de cámara denegado. Habilítelo en la configuración del navegador."),
                    { type: "warning" }
                );
            } else if (isNotFound) {
                this.notification.add(
                    _t("No se encontró ninguna cámara en el dispositivo."),
                    { type: "warning" }
                );
            }
            // El usuario canceló el diálogo: no mostramos error
        }
    }

    async onBarcodeScanned({ detail: { barcode } }) {
        await this.processBarcode(barcode);
    }

    async processBarcode(barcode) {
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
