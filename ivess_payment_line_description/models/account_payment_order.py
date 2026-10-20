from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    def action_edit_line_description(self):
        self.ensure_one()
        return {
            'name': "Editar descripción de líneas de pago",
            'type': 'ir.actions.act_window',
            'res_model': 'payment.line.description.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_order_id': self.id},
        }
