# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    repair_equipment_type = fields.Selection(
        selection=[
            ('frio_calor', 'Frío/Calor'),
            ('cafetera', 'Máquina de café/Cafetera'),
        ],
        string="Tipo de equipo para reparación",
    )
