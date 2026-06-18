# -*- coding: utf-8 -*-
from odoo import models, fields


class QualityPoint(models.Model):
    _inherit = 'quality.point'


    is_frio_calor = fields.Boolean(
        string="Es operación Frío/Calor",
        default=False,
    )
