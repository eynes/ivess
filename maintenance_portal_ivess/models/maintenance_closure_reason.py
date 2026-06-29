# -*- coding: utf-8 -*-
from odoo import models, fields


class MaintenanceClosureReason(models.Model):
    _name = 'maintenance.closure.reason'
    _description = 'Motivo de Cierre de Mantenimiento'
    _order = 'name'

    name = fields.Char(string='Motivo', required=True)

    parent_id = fields.Many2one(
        'maintenance.closure.reason',
        string='Categoría padre',
        ondelete='restrict',
        index=True,
    )
    child_ids = fields.One2many(
        'maintenance.closure.reason',
        'parent_id',
        string='Subcategorías',
    )
    is_parent = fields.Boolean(
        string='Es categoría',
        compute='_compute_is_parent',
        store=True,
    )

    def _compute_is_parent(self):
        for rec in self:
            rec.is_parent = not rec.parent_id
