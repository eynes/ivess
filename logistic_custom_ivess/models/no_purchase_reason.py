from odoo import models, fields, _, api
from odoo.exceptions import ValidationError


class NoPurchaseReason(models.Model):
    _name = 'no.purchase.reason'
    _description = 'Motivo de No Compra'
    _rec_name = 'reason'
    _order = 'order ASC'
    _sql_constraints = [
        ('unique_code', 'unique(code)', 'The code must be unique!'),
    ]

    reason = fields.Char(
        string='Reason',
        required=True,
        size=50,
        help="Reason why the visit could not be completed."
    )
    is_rake = fields.Boolean(
        string="Is Rake",
    )
    code = fields.Char(
        string="Code",
        required=True,
    )
    order = fields.Integer(
        string="Order",
        required=True,
    )

    @api.constrains('order')
    def _check_unique_order(self):
        for rec in self:
            if rec.order is not None:
                domain = [('order', '=', rec.order)]
                if rec.id:
                    domain.append(('id', '!=', rec.id))
                if self.search_count(domain):
                    raise ValidationError(_("The order must be unique."))
