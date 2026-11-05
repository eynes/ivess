from odoo import fields, models


class ResCityNeighborhood(models.Model):
    _name = "res.city.neighborhood"
    _description = "Barrio"
    _order = "city_id, name"

    name = fields.Char(string="Barrio", required=True)
    city_id = fields.Many2one(
        "res.city",
        string="Ciudad",
        required=True,
        ondelete="cascade",
        index=True,
    )
    _name_city_uniq = models.Constraint(
        "unique(name, city_id)",
        "Ese barrio ya existe en la ciudad.",
    )


class ResCity(models.Model):
    _inherit = "res.city"

    neighborhood_ids = fields.One2many(
        "res.city.neighborhood",
        "city_id",
        string="Barrios",
    )


class DeliveryRouteNumber(models.Model):
    _inherit = "delivery.route.number"

    neighborhood_ids = fields.Many2many(
        "res.city.neighborhood",
        "delivery_route_number_neighborhood_rel",
        "route_id",
        "neighborhood_id",
        string="Barrios",
    )
