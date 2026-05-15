# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class MaintenanceStage(models.Model):
    _inherit = 'maintenance.stage'

    in_progress = fields.Boolean(
        string='En Progreso',
        help='Al llegar a esta etapa se reservará el stock de los materiales de la solicitud.',
    )
