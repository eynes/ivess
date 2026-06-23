# -*- coding: utf-8 -*-
from odoo import models, fields, api


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
    
    message_type = fields.Selection(
        selection=[
            ('LL', 'Llamado'),
            ('CI', 'Carta Interna'),
        ],
        string='Tipo de Mensaje',
    )
    message_text = fields.Text(
        string='Mensaje',
    )

    def action_open_message_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mensaje',
            'res_model': 'res.partner.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }
