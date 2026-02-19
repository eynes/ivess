# Copyright 2018 Creu Blanca
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockRequestOrder(models.Model):
    _inherit = "stock.request.order"
    _description = "Stock Request Order"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        location = None
        if self.env.user.location_id:
            location = self.env.user.location_id
        if location:
            res["warehouse_id"] = False
            res["location_id"] = location.id
        return res
