from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockLot(models.Model):
    _inherit = 'stock.lot'

    brand = fields.Char(string="Marca")
    model = fields.Char(string="Modelo")
    registration_date = fields.Date(string="Fecha de registro")
