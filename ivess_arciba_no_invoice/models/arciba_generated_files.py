from odoo import fields, models


class ArcibaGeneratedFiles(models.Model):
    _inherit = "arciba.generated.files"

    notes = fields.Text(
        readonly=True,
        help="Warnings found when the file was generated.",
    )
