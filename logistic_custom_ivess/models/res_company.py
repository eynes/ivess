from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    customer_sequence_id = fields.Many2one('ir.sequence', string="Customer sequence")
