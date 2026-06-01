# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    aguas_fc_taller_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación Taller FC',
        domain=[('usage', '=', 'internal')],
        help='Ubicación destino para los equipos que ingresan desde Aguas (AC/TALLER EQUIPOS FC).',
    )
    aguas_fc_picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Tipo de Operación Aguas FC',
        domain=[('code', '=', 'internal')],
        help='Tipo de operación para los traslados de ingreso desde Aguas (Traslados Internos).',
    )
    aguas_fc_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto Equipo FC',
        domain=[('tracking', '=', 'serial')],
        help='Producto genérico utilizado para los equipos de frío-calor (Equipo Frio Calor).',
    )
