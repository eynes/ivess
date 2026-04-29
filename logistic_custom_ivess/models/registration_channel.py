from odoo import models, fields


class RegistrationChannel(models.Model):
    _name = 'registration.channel'
    _description = 'Registration Channel'

    name = fields.Char(string="Name", required=True)
