from odoo import fields, models


class RubroCreditoFiscal(models.Model):
    _name = "rubro.credito.fiscal"
    _description = "Rubro Crédito Fiscal"

    name = fields.Char(string="Nombre", required=True)
