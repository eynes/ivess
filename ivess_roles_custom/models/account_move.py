from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        user = self.env.user
        is_purchase_user_only = user.has_group(
            "purchase.group_purchase_user"
        ) and not (
            user.has_group("purchase.group_purchase_manager")
            or user.has_group("base.group_system")
        )
        if is_purchase_user_only and any(
            move.move_type in ("in_invoice", "in_refund") for move in self
        ):
            group = self.env.ref("purchase.group_purchase_user")
            raise UserError(
                _(
                    "El grupo '%(group)s' no tiene permisos para validar "
                    "facturas de proveedor.",
                    group=group.full_name,
                )
            )
        return super().action_post()
