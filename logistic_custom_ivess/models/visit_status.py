from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class VisitStatus(models.Model):
    _name = 'visit.status'
    _description = 'Visit Status'
    _rec_name = 'status_name'

    status_name = fields.Char(
        string='Status',
        required=True,
        size=25
    )
    requires_reason = fields.Boolean(
        string="Requiere Motivo",
        help=_("Indicates if this visit status requires a reason for no purchase.")
    )
