from odoo import fields, models


class PartnerDistribution(models.Model):
    _inherit = 'partner.distribution'

    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string='Lista de Precio',
        related='distribution.pricelist_id',
        store=True,
        index='btree_not_null',
    )


class ZoneConsultWizardLine(models.TransientModel):
    _inherit = 'zone.consult.wizard.line'

    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string='Lista de Precio',
        related='template_id.pricelist_id',
    )
