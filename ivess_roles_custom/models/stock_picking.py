from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        """
        CSV filas 6, 17, 18 — Validación de transferencias:
          · Validar Recepción   → purchase_manager, stock_user, stock_manager, system
          · Validar Recepciones → stock_user (Actualizar), stock_manager, system
          · Validar Entregas    → stock_user (Actualizar), stock_manager, system
        El Usuario Compras (purchase.group_purchase_user) NO puede validar
        ningún tipo de picking (fila 6: ❌ No).
        """
        user = self.env.user
        is_purchase_user_only = user.has_group(
            "purchase.group_purchase_user"
        ) and not (
            user.has_group("purchase.group_purchase_manager")
            or user.has_group("base.group_system")
        )
        if is_purchase_user_only and any(
            p.picking_type_code == "incoming" for p in self
        ):
            group = self.env.ref("purchase.group_purchase_user")
            raise UserError(
                _(
                    "El grupo '%(group)s' no tiene permisos para validar "
                    "recepciones de productos.",
                    group=group.full_name,
                )
            )
        allowed = (
            user.has_group("stock.group_stock_user")
            or user.has_group("stock.group_stock_manager")
            or user.has_group("purchase.group_purchase_manager")
            or user.has_group("base.group_system")
        )
        if not allowed:
            raise UserError(
                _("No tiene permisos para validar transferencias de stock.")
            )
        return super().button_validate()
