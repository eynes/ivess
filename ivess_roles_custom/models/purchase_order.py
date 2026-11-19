from odoo import _, fields, models
from odoo.exceptions import UserError

APPROVER_GROUP = "ivess_roles_custom.group_purchase_approver"


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _ivess_over_approval_limit(self):
        """True si la orden alcanza el límite de doble validación de su compañía.

        Mismo cálculo que purchase.order._approval_allowed() de Odoo.
        """
        self.ensure_one()
        company = self.company_id
        if company.po_double_validation != "two_step":
            return False
        limit = self.env.company.currency_id._convert(
            company.po_double_validation_amount,
            self.currency_id,
            company,
            self.date_order or fields.Date.today(),
        )
        return self.amount_total >= limit

    def _approval_allowed(self):
        """
        CSV fila 4 — "Confirmar Orden de Compra" + doble validación por monto.

        Quién puede llevar la orden a "Orden de compra" (confirmar o aprobar):
          · Aprobador de órdenes de compra (grupo de este módulo): cualquier monto.
          · Administrador de Compras / Administrador TOTAL: si la orden no alcanza
            el límite de doble validación de la compañía. Si lo alcanza, al
            confirmar queda "Por aprobar".
          · Usuario Compras: nunca. Al confirmar, la orden queda "Por aprobar"
            para que la apruebe un Administrador de Compras (o el Aprobador,
            si alcanza el límite).

        Odoo estándar deja pasar cualquier monto a todo Administrador de Compras.
        Como en Ivess todos los compradores lo son (es el grupo que confirma),
        la doble validación no se aplicaba nunca.

        Lo usan button_confirm (aprobar directo o "Por aprobar"), button_approve
        y write(state='purchase') del módulo purchase, así que la regla vale
        también vía API/XML-RPC.
        """
        self.ensure_one()
        user = self.env.user
        if user.has_group(APPROVER_GROUP):
            return True
        if not (
            user.has_group("purchase.group_purchase_manager")
            or user.has_group("base.group_system")
        ):
            return False
        return not self._ivess_over_approval_limit()

    def button_approve(self, force=False):
        """
        El estándar descarta en silencio las órdenes que el usuario no puede
        aprobar: apretaba "Aprobar orden" y no pasaba nada. Acá se avisa.
        Solo se controla lo que está "Por aprobar"; button_confirm llama a este
        método con órdenes en borrador ya filtradas por _approval_allowed().
        """
        if not self.env.su:
            denied = self.filtered(
                lambda po: po.state == "to approve" and not po._approval_allowed()
            )
            if denied:
                raise UserError(
                    _(
                        "No podés aprobar %(orders)s. Las órdenes que alcanzan el "
                        "límite de doble validación solo las aprueba el grupo "
                        "'Aprobador de órdenes de compra'; las demás, un "
                        "Administrador de Compras.",
                        orders=", ".join(denied.mapped("name")),
                    )
                )
        return super().button_approve(force=force)
