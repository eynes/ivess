from odoo import api, fields, models
from odoo.addons.account.report.account_invoice_report import (
    AccountInvoiceReport as BaseAccountInvoiceReport,
)
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    area_id = fields.Many2one(
        'product.area',
        string='Rubro',
        readonly=True,
    )
    rubro_credito_fiscal_id = fields.Many2one(
        'rubro.credito.fiscal',
        string='Rubro Crédito Fiscal',
        readonly=True,
    )

    # _depends es un atributo de clase plano (no se mergea al heredar, ver
    # odoo/orm/models.py), así que hay que reconstruirlo incluyendo el del
    # core: si se pisa, se pierde el flush de account.move/account.move.line
    # previo a cada search/read y se pueden leer datos desactualizados.
    _depends = {
        **BaseAccountInvoiceReport._depends,
        'product.template': [
            *BaseAccountInvoiceReport._depends.get('product.template', ()),
            'area_id',
            'rubro_credito_fiscal_id',
        ],
    }

    @api.model
    def _select(self) -> SQL:
        # product_template ya viene joineado como "template" en el _from() del
        # core (es de donde sale product_categ_id), así que alcanza con sumar
        # las dos columnas al SELECT.
        return SQL(
            '''%s,
                template.area_id                                AS area_id,
                template.rubro_credito_fiscal_id                AS rubro_credito_fiscal_id
            ''',
            super()._select(),
        )
