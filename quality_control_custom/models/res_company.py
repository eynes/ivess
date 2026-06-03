# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    tercerizacion_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación Tercerización',
        domain=[('usage', '=', 'internal')],
        help='Ubicación de destino para traslados generados al tercerizar un equipo.',
    )
