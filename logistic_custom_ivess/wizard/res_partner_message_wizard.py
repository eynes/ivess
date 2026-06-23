from odoo import api, fields, models


class ResPartnerMessageWizard(models.TransientModel):
    _name = 'res.partner.message.wizard'
    _description = 'Partner Message Wizard'

    partner_distribution_id = fields.Many2one('partner.distribution', required=True)
    message_type = fields.Selection(
        selection=[
            ('LL', 'Llamado'),
            ('CI', 'Carta Interna'),
        ],
        string='Tipo de Mensaje',
        required=True,
    )
    message_text = fields.Text(string='Mensaje')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        distribution_id = self.env.context.get('active_id')
        if distribution_id:
            res['partner_distribution_id'] = distribution_id
            distribution = self.env['partner.distribution'].browse(distribution_id)
            res['message_type'] = distribution.message_type or False
            res['message_text'] = distribution.message_text or False
        return res

    def action_confirm(self):
        self.partner_distribution_id.write({
            'message_type': self.message_type,
            'message_text': self.message_text,
        })
