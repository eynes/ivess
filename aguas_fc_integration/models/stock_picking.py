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

    aguas_fc_ref_externa_anulada = fields.Char(
        string='Referencia externa anulada',
        index=True,
        copy=False,
        readonly=True,
        help='Referencia de Loop que tenía la carga cuando se anuló. Al anular '
             'se libera aguas_fc_ref_externa para poder reusarla.',
    )
    aguas_fc_anulacion_id = fields.Many2one(
        'stock.picking',
        string='Anulada por',
        copy=False,
        readonly=True,
        help='Traslado de devolución (reparto -> expedición) que anuló esta carga.',
    )
    aguas_fc_reemplazo_id = fields.Many2one(
        'stock.picking',
        string='Reemplazada por',
        copy=False,
        readonly=True,
        help='Carga nueva que reemplazó a esta.',
    )

    _sql_constraints = [
        ('aguas_fc_ref_externa_uniq',
         'unique(aguas_fc_ref_externa)',
         'Ya existe un traslado registrado con esa referencia externa de Loop.'),
    ]
