from odoo import models


class AccountFullReconcile(models.Model):
    _inherit = "account.full.reconcile"

    def _update_checks_on_reconcile(self):
        """Salta la revisión de cheques en las conciliaciones del Cierre
        Mensual que no tocan ningún asiento con cheques.

        l10n_ar_reconciliation recorre cada conciliación total buscando
        cheques emitidos en sus líneas o cheques de terceros depositados con
        sus asientos; si no hay ninguno no hace nada. El cierre le pasa en el
        contexto todos los asientos que tienen cheques, de modo que acá solo
        se evita buscar lo que de todos modos no existe.
        """
        check_move_ids = self.env.context.get("ivess_summary_check_move_ids")
        if check_move_ids is not None and not (
            check_move_ids.intersection(self.reconciled_line_ids.move_id.ids)
        ):
            return None
        return super()._update_checks_on_reconcile()
