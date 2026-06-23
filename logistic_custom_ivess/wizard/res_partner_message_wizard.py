from odoo import api, fields, models


class ResPartnerMessageWizard(models.TransientModel):
    _name = 'res.partner.message.wizard'
    _description = 'Partner Message Wizard'

    partner_id = fields.Many2one('res.partner', required=True)
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
        partner_id = self.env.context.get('active_id')
        if partner_id:
            res['partner_id'] = partner_id
            partner = self.env['res.partner'].browse(partner_id)
            res['message_type'] = partner.message_type or False
            res['message_text'] = partner.message_text or False
        return res

    def action_confirm(self):
        self.partner_id.write({
            'message_type': self.message_type,
            'message_text': self.message_text,
        })
