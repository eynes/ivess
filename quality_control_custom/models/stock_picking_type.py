# -*- coding: utf-8 -*-
from odoo import models, fields


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_frio_calor = fields.Boolean(
        string="Es operación Frío/Calor",
        default=False,
    )
