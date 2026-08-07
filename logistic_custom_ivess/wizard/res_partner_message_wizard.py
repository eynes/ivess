from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartnerMessageWizard(models.TransientModel):
    _name = 'res.partner.message.wizard'
    _description = 'Partner Message Wizard'

    partner_distribution_id = fields.Many2one('partner.distribution', required=True)
    route_id = fields.Many2one('delivery.route', string='Recorrido', readonly=True, required=True)
    message_id = fields.Many2one('partner.distribution.message')
    message_text = fields.Text(string='Mensaje')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        distribution_id = self.env.context.get('active_id')
        if distribution_id:
            distribution = self.env['partner.distribution'].browse(distribution_id)
            route = distribution._get_target_route()
            if not route:
                raise UserError(_(
                    "No hay un recorrido en curso ni programado para la plantilla %(template)s. "
                    "No se puede asociar un mensaje."
                ) % {'template': distribution.distribution.name})
            res['partner_distribution_id'] = distribution_id
            res['route_id'] = route.id
            message = distribution.message_ids.filtered(lambda m: m.route_id == route)
            res['message_id'] = message.id if message else False
            res['message_text'] = message.message_text if message else False
        return res

    def action_confirm(self):
        if self.message_id:
            self.message_id.write({
                'message_text': self.message_text,
            })
        else:
            self.env['partner.distribution.message'].create({
                'partner_distribution_id': self.partner_distribution_id.id,
                'route_id': self.route_id.id,
                'message_text': self.message_text,
            })
