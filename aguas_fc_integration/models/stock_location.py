# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    aguas_idreparto = fields.Char(
        string='ID Reparto Aguas',
        help='ID del reparto en el sistema Aguas (Mobeus) que corresponde a esta ubicación.',
    )
