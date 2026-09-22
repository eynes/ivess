import {BankRecButtonList} from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import {patch} from "@web/core/utils/patch";

/**
 * El dialogo "Buscar: Apuntes contables por conciliar" (boton Conciliar del menu
 * de la transaccion) trae, ademas de contrapartidas validas, los propios
 * asientos que Odoo genera automaticamente por cada linea de extracto (la
 * pata del banco y su contrapartida en la cuenta provisoria): esos nunca son
 * una contrapartida valida de otra transaccion.
 *
 * account.move.line.statement_line_id es related de move_id.statement_line_id
 * (store=True), asi que queda seteado en TODAS las lineas del asiento que
 * genera una transaccion de extracto, este o no conciliada. Alcanza con
 * descartar por ese campo para sacarlas del buscador.
 *
 * Parcheamos aca en lugar de en l10n_ar_eynes_accountant (que ya patchea el
 * mismo componente para el filtro de cuenta provisoria) para no mezclar una
 * regla generica del widget de conciliacion con la localizacion argentina.
 */
patch(BankRecButtonList.prototype, {
    getReconcileButtonDomain() {
        return [...super.getReconcileButtonDomain(), ["statement_line_id", "=", false]];
    },
});
