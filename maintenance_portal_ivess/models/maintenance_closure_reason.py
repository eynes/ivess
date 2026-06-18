# -*- coding: utf-8 -*-
from odoo import models, fields


class MaintenanceClosureReason(models.Model):
    _name = 'maintenance.closure.reason'
    _description = 'Motivo de Cierre de Mantenimiento'
    _order = 'name'

    name = fields.Char(string='Motivo', required=True)
