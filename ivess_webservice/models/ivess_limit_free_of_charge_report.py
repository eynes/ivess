from odoo import api, fields, models, tools

class IvessLimitFreeOfChargeReport(models.Model):
    _name = "ivess.limit.free.of.charge.report"
    _description = "Vista SQL de límites de sin cargo expuesta al middleware Ivess"
    _auto = False
    
    default_code = fields.Char(readonly=True)