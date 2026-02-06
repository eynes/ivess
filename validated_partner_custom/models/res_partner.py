from odoo import models, fields, api, _
# from odoo.tools.safe_eval import safe_eval
from collections import defaultdict

class ResPartner(models.Model):
    _inherit = 'res.partner'

    validated_supplier = fields.Boolean(
        string="Validated Supplier",
        help=_("Indicates whether the supplier has been validated by the Administration team."),
        tracking=True
    )