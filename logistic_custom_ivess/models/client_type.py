from odoo import models, fields, _
from odoo.exceptions import UserError


class ClientType(models.Model):
    _name = 'client.type'
    _description = 'Client Type'
    _rec_name = 'description'

    code = fields.Integer(string="Code")
    description = fields.Text(string="Description")

    _sql_constraints = [
        (
            "unique_code_record",
            "unique(code)",
            _("The code must be unique"),
        ),
    ]

    def unlink(self):
        for rec in self:
            partner_count = self.env['res.partner'].search_count([('partner_type_id', '=', rec.id)])
            if partner_count > 0:
                raise UserError(_(
                    "You cannot delete the client type '%s' because it is assigned to %s partner(s)."
                ) % (rec.code, partner_count))
        return super().unlink()
