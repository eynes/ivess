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
