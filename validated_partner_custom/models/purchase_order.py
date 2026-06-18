from odoo import models, _
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def action_create_invoice(self):
        for order in self:
            partner = order.partner_id
            if not partner.validated_supplier and partner.supplier_invoice_count > 0:
                 raise UserError(
                    _(
                        "The selected supplier '%s' is not validated by the Administration team. "
                        "Please request validation."
                    ) % partner.display_name
                )
        return super(PurchaseOrder, self).action_create_invoice()
