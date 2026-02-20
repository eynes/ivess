# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'
    _description = 'Partner'

    distributions_ids = fields.One2many('partner.distribution', 'partner_id', string='Distributions', tracking=True)

    
class PartnerDistributions(models.Model):
    _name = 'partner.distribution'
    _description = 'Distributions'

    distribution = fields.Many2one('template.delivery.route', tracking=True)
    visit_day = fields.Selection(
        related='distribution.day',
        string='Visit Day',
        tracking=True,
    )
    frequency = fields.Selection(
        selection=[
            ('weekly', 'Weekly'),
            ('biweekly', 'Biweekly'),
            ('monthly', 'Monthly')
        ],
        default=False,
        string='Frequency',
        tracking=True,
    )
    partner_id = fields.Many2one('res.partner', string='Partner', tracking=True)