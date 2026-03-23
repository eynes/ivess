from odoo import models, fields, api, _


class ResPartnerWaterConsumption(models.Model):
    _name = 'res.partner.water.consumption'
    _description = 'Monthly Water Consumption per Customer'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, ondelete='cascade')
    month = fields.Integer(string='Month', required=True)
    year = fields.Integer(string='Year', required=True)
    consumption_liters = fields.Float(string='Consumption (liters)', default=0.0)
    name = fields.Char(string='Description', compute='_compute_name', store=True)

    _sql_constraints = [
        ('unique_customer_month_year',
         'unique(partner_id, month, year)',
         _('A consumption record for this customer already exists for this month and year.'))
    ]

    @api.depends('partner_id', 'month', 'year')
    def _compute_name(self):
        for rec in self:
            if rec.partner_id and rec.month and rec.year:
                rec.name = rec.partner_id.name + ' - ' + str(rec.month).zfill(2) + '/' + str(rec.year)
            else:
                rec.name = '-'
