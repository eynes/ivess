# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'
    _description = 'Users'

    location_id = fields.Many2one(
        'stock.location',
        string='Default Stock Location',
        help='Default stock location for this user.',
    )
    