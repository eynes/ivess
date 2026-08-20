from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    fiscal_type = fields.Selection(
        selection_add=[('internal_voucher', 'Comprobante Interno')],
        ondelete={'internal_voucher': 'set default'},
    )
