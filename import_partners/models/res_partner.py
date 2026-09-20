from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    codigo_bejerman = fields.Char(index=True)
    customer_code = fields.Char(index=True)

    csv_inherit_commercial = fields.Boolean(
        string='Hereda comercial de madre (importación CSV)', copy=False,
        help='Conserva el tipo de empresa, pero usa el comercial de la madre.',
    )

    @api.depends('is_company', 'parent_id.commercial_partner_id', 'csv_inherit_commercial')
    def _compute_commercial_partner(self):
        super()._compute_commercial_partner()
        for partner in self:
            if partner.csv_inherit_commercial and partner.parent_id:
                partner.commercial_partner_id = partner.parent_id.commercial_partner_id

    def do_update_from_padron(self, *args, **kwargs):
        if self.env.context.get('ivess_csv_import'):
            return False
        return super().do_update_from_padron(*args, **kwargs)
