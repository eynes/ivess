from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class PaymentLineDescriptionWizard(models.TransientModel):
    _name = 'payment.line.description.wizard'
    _description = 'Editar descripción de líneas de pago'

    payment_order_id = fields.Many2one(
        comodel_name='account.payment.order',
        string='Orden de pago',
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name='payment.line.description.wizard.line',
        inverse_name='wizard_id',
        string='Líneas',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['account.payment.order'].browse(
            res.get('payment_order_id')
        )
        if order and 'line_ids' in fields_list:
            res['line_ids'] = [
                (0, 0, {'payment_line_id': line.id, 'name': line.name})
                for line in order.payment_mode_line_ids
            ]
        return res

    def action_apply(self):
        self.ensure_one()
        order = self.payment_order_id
        if order.state == 'draft':
            raise UserError(
                "En borrador la descripción se edita directamente en las "
                "líneas de pago."
            )
        changes = []
        for line in self.line_ids:
            payment_line = line.payment_line_id
            if (payment_line.name or '') == (line.name or ''):
                continue
            changes.append(
                (
                    payment_line.payment_mode_id.display_name,
                    payment_line.name or '',
                    line.name or '',
                )
            )
            payment_line.name = line.name
        if changes:
            body = Markup("{}{}").format(
                "Descripción de línea de pago editada:",
                Markup("").join(
                    Markup("<br/>{}: “{}” → “{}”").format(journal, old, new)
                    for journal, old, new in changes
                ),
            )
            order.message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}


class PaymentLineDescriptionWizardLine(models.TransientModel):
    _name = 'payment.line.description.wizard.line'
    _description = 'Editar descripción de líneas de pago (línea)'

    wizard_id = fields.Many2one(
        comodel_name='payment.line.description.wizard',
        required=True,
        ondelete='cascade',
    )
    payment_line_id = fields.Many2one(
        comodel_name='account.payment.mode.line',
        string='Línea de pago',
        required=True,
    )
    payment_mode_id = fields.Many2one(
        related='payment_line_id.payment_mode_id', string='Método de pago'
    )
    date = fields.Date(related='payment_line_id.date', string='Fecha de pago')
    amount = fields.Float(
        related='payment_line_id.amount', string='Importe', digits=(16, 2)
    )
    name = fields.Text(string='Descripción')
