from odoo import models, fields


class DeliveryRouteRegion(models.Model):
    _name = 'delivery.route.region'
    _description = 'Delivery Route Region'

    name = fields.Char(string="Nombre", required=True)
    supervisor_id = fields.Many2one(
        'res.partner',
        string='Supervisor',
    )
