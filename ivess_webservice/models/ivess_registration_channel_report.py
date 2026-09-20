from odoo import api, models

class IvessRegistrationChannel(models.Model):
    _name = "ivess.registration.channel.report"
    _description = "Servicio de canales de alta expuesto al middleware Ivess"

    @api.model
    def get_registration_channels(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        channels = self.env["registration.channel"].search([])
        return [
            {
                "registration_channel_id": channel.id,
                "name": channel.name
            }
            for channel in channels
        ]
