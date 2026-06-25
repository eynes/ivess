from odoo import _, fields, models


class DeliveryRouteBisWizard(models.TransientModel):
    _name = 'delivery.route.bis.wizard'
    _description = 'Wizard Crear Ruta Bis'

    route_id = fields.Many2one('delivery.route', required=True)
    delivery_number_id = fields.Many2one(
        'delivery.route.number',
        string='Número de Reparto',
        required=True,
    )

    def action_confirm(self):
        new_route = self.route_id.copy()
        new_route.write({
            'name': f"{self.route_id.name}-bis",
            'delivery_number_id': self.delivery_number_id.id,
            'template_delivery_route_id': False,
            'truck_id': self.delivery_number_id.truck_id.id or False,
        })
        new_route.message_post(
            body=_(
                "Esta ruta fue generada mediante la acción 'Crear ruta Bis' "
                "asociando el reparto %s."
            ) % self.delivery_number_id.display_name,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'delivery.route',
            'res_id': new_route.id,
            'view_mode': 'form',
        }
