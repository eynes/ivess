from odoo import fields, models


class PartnerDistribution(models.Model):
    _inherit = "partner.distribution"

    partner_condicion = fields.Selection(
        related="partner_id.condicion",
        string="Condición",
        store=True,
    )
