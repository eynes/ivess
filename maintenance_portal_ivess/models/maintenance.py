# -*- coding: utf-8 -*-
import logging
from odoo import models, api, fields
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
