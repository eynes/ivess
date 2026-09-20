from odoo import api, fields, models


class ProductArea(models.Model):
    _inherit = "product.area"

    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} - {rec.name}"
