import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { formatMonetary } from "@web/views/fields/formatters";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

/**
 * "Ver visitas" de la ficha del cliente: la lista lleva arriba la deuda actual
 * del cliente (ventas, frío/calor y total) y el botón Adeudado, siempre
 * visibles aunque se filtren visitas de otro mes. El cliente sale de
 * active_id, igual que el dominio de la acción.
 */
export class VisitasDeudaListController extends ListController {
    static template = "ivess_partner_custom.VisitasDeudaListView";

    setup() {
        super.setup();
        this.deuda = useState({ datos: false });
        onWillStart(() => this.cargarDeuda(this.props.context.active_id));
        onWillUpdateProps((nextProps) => this.cargarDeuda(nextProps.context.active_id));
    }

    async cargarDeuda(partnerId) {
        this.deuda.datos = partnerId
            ? await this.orm.call("res.partner", "get_deuda_visitas", [partnerId])
            : false;
    }

    formatear(importe) {
        return formatMonetary(importe, { currencyId: this.deuda.datos.currency_id });
    }

    async verAdeudado() {
        const accion = await this.orm.call("res.partner", "open_follow_up_report", [
            [this.deuda.datos.id],
        ]);
        await this.actionService.doAction(accion);
    }
}

registry.category("views").add("visitas_deuda_list", {
    ...listView,
    Controller: VisitasDeudaListController,
});
