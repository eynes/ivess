# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    aguas_fc_ref_externa = fields.Char(
        string='Referencia externa Loop',
        index=True,
        copy=False,
        help='Identificador único de la carga enviado por Loop. Evita que un '
             'reintento del mismo pedido duplique el movimiento de stock.',
    )

    _sql_constraints = [
        ('aguas_fc_ref_externa_uniq',
         'unique(aguas_fc_ref_externa)',
         'Ya existe un traslado registrado con esa referencia externa de Loop.'),
    ]
