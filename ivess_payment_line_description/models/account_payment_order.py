from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    is_other_payment_journal = fields.Boolean(
        compute='_compute_is_other_payment_journal'
    )

    @api.depends('journal_id', 'company_id.other_payment_journal_id')
    def _compute_is_other_payment_journal(self):
        for order in self:
            other_journal = order.company_id.other_payment_journal_id
            order.is_other_payment_journal = bool(
                other_journal and order.journal_id == other_journal
            )

    def action_edit_line_description(self):
        self.ensure_one()
        if not self.is_other_payment_journal:
            raise UserError(
                "La descripción solo se puede editar desde este botón en "
                "pagos del diario de Otros Pagos."
            )
        return {
            'name': "Editar descripción de líneas de pago",
            'type': 'ir.actions.act_window',
            'res_model': 'payment.line.description.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_order_id': self.id},
        }
