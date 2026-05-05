# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    terciarizacion_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación Terciarización',
        domain=[('usage', '=', 'internal')],
        help='Ubicación de destino para traslados generados al terciarizar un equipo.',
    )
