# -*- coding: utf-8 -*-
import logging
from odoo import models, api, fields, _
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class MaintenanceTeams(models.Model):

    _inherit = 'maintenance.team'

    is_workshop = fields.Boolean(string='Es taller', default=False)
    is_internal_maintenance = fields.Boolean(string='Es mantenimiento interno', default=False)

class MaintenanceRequest(models.Model):

    _inherit = 'maintenance.request'

    is_workshop = fields.Boolean(string='Es taller', related='maintenance_team_id.is_workshop', store=True)
    is_internal_maintenance = fields.Boolean(string='Es mantenimiento interno', related='maintenance_team_id.is_internal_maintenance', store=True)

    closure_reason_id = fields.Many2one(
        'maintenance.closure.reason',
        string='Motivo de cierre',
        ondelete='restrict',
    )

    department_id = fields.Many2one(
        'hr.department',
        string='Departamento'
    )

    def action_mark_as_repaired(self):
        repaired_stage = self.env['maintenance.stage'].search(
            [('done', '=', True)], order='sequence asc', limit=1
        )
        for rec in self:
            if not rec.closure_reason_id:
                raise UserError(_('Debe seleccionar un motivo de cierre antes de marcar como terminado.'))
            if repaired_stage:
                rec.stage_id = repaired_stage
