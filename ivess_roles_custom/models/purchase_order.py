from odoo import _, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def button_confirm(self):
        """
        CSV fila 4 — "Confirmar Orden de Compra":
        Solo el Administrador de Compras (purchase.group_purchase_manager)
        y el Administrador TOTAL (base.group_system) pueden confirmar.
        El Usuario Compras (purchase.group_purchase_user) puede crear y
        editar RFQs pero no confirmarlas → restricción aplicada aquí a nivel
        de modelo para que sea efectiva también vía API/XML-RPC.
        """
        user = self.env.user
        if not (
            user.has_group("purchase.group_purchase_manager")
            or user.has_group("base.group_system")
        ):
            raise UserError(
                _(
                    "Solo el Administrador de Compras puede confirmar "
                    "órdenes de compra."
                )
            )
        return super().button_confirm()
