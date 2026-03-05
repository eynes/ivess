from odoo import models, fields, _, api
from odoo.exceptions import ValidationError


class ReplacementReason(models.Model):
    _name = 'replacement.reason'
    _description = 'Replacement Reason'
    _order = 'sequence ASC'
    _rec_name = 'reason'
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The code must be unique.'),
    ]

    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
    )
    reason = fields.Char(
        string='Reason',
        required=True,
        size=50
    )
    sequence = fields.Integer(
        string='Order',
        default=0
    )

    @api.constrains('sequence')
    def _check_unique_sequence(self):
        for rec in self:
            if rec.sequence is not None:
                domain = [('sequence', '=', rec.sequence)]
                if rec.id:
                    domain.append(('id', '!=', rec.id))
                if self.search_count(domain):
                    raise ValidationError(_("The order must be unique."))
