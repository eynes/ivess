# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from .repair_order import FRIO_CALOR_STAGES


class RepairOrderStageLog(models.Model):
    _name = 'repair.order.stage.log'
    _description = 'Historial de Etapas - Orden de Reparación'
    _order = 'date_start asc'

    repair_id = fields.Many2one(
        'repair.order',
        string='Orden de Reparación',
        required=True,
        ondelete='cascade',
        index=True,
    )
    stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string='Etapa',
        required=True,
    )
    date_start = fields.Datetime(string='Inicio', required=True)
    date_end = fields.Datetime(string='Fin')
    duration = fields.Float(
        string='Duración (hs)',
        compute='_compute_duration',
        store=True,
    )
    duration_display = fields.Char(
        string='Duración',
        compute='_compute_duration_display',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
    )

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                delta = rec.date_end - rec.date_start
                rec.duration = delta.total_seconds() / 3600.0
            else:
                rec.duration = 0.0

    @api.depends('date_start', 'date_end')
    def _compute_duration_display(self):
        for rec in self:
            if not rec.date_end:
                rec.duration_display = _('En curso')
                continue
            total_seconds = int((rec.date_end - rec.date_start).total_seconds())
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            parts = []
            if days:
                parts.append(f'{days}d')
            if hours:
                parts.append(f'{hours}h')
            if minutes:
                parts.append(f'{minutes}m')
            rec.duration_display = ' '.join(parts) or '< 1m'
