# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models

TEAM_TYPE_SELECTION = [
    ('workshop', 'Taller Mecánico'),
    ('maintenance', 'Mantenimiento'),
    ('other', 'Otro'),
]


class HelpdeskTeam(models.Model):
    _inherit = 'helpdesk.team'

    use_maintenance_orders = fields.Boolean(string='Maintenance Orders')
    team_type = fields.Selection(
        selection=TEAM_TYPE_SELECTION,
        string='Tipo',
    )
