# -*- coding: utf-8 -*-
from odoo import models, fields


class RepairOutsourceReason(models.Model):
    _name = 'repair.outsource.reason'
    _description = 'Razón de Tercerización'
    _order = 'name'

    name = fields.Char(string='Razón', required=True, translate=True)
    active = fields.Boolean(default=True)
