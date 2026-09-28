from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.account.report.account_invoice_report import (
    AccountInvoiceReport as BaseAccountInvoiceReport,
)


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    area_id = fields.Many2one(
        "product.area",
        string="Rubro",
        readonly=True,
    )
    rubro_credito_fiscal_id = fields.Many2one(
        "rubro.credito.fiscal",
        string="Rubro Crédito Fiscal",
        readonly=True,
    )
    iva_compras_tax_id = fields.Many2one(
        "account.tax",
        string="IVA Compras",
        readonly=True,
        domain=[
            ("tax_group_id.group_type", "=", "vat"),
            ("type_tax_use", "=", "purchase"),
        ],
    )
    iva_compras_amount = fields.Float(
        string="Monto IVA Compras",
        readonly=True,
    )

    # _depends es un atributo de clase plano (no se mergea al heredar, ver
    # odoo/orm/models.py), así que hay que reconstruirlo incluyendo el del
    # core: si se pisa, se pierde el flush de account.move/account.move.line
    # previo a cada search/read y se pueden leer datos desactualizados.
    _depends = {
        **BaseAccountInvoiceReport._depends,
        "product.template": [
            *BaseAccountInvoiceReport._depends.get("product.template", ()),
            "area_id",
            "rubro_credito_fiscal_id",
        ],
        "account.move.line": [
            *BaseAccountInvoiceReport._depends.get("account.move.line", ()),
            "tax_ids",
        ],
        "account.tax": ["tax_group_id", "amount"],
        "account.tax.group": ["group_type"],
    }

    @api.model
    def _select(self) -> SQL:
        # product_template ya viene joineado como "template" en el _from() del
        # core (es de donde sale product_categ_id), así que alcanza con sumar
        # las columnas al SELECT. El impuesto y su alícuota salen del LATERAL
        # JOIN agregado en _from() (iva_compras_tax): una línea de producto
        # puede tener más de un impuesto (IVA + percepción, etc.), pero como
        # mucho un IVA de compras, así que el LIMIT 1 de ese JOIN es seguro.
        # El monto se calcula igual que price_subtotal_to_PDF en
        # l10n_ar_eynes (base * alícuota/100): todo el IVA argentino
        # cargado es de tipo "percent".
        return SQL(
            """%s,
                template.area_id                   AS area_id,
                template.rubro_credito_fiscal_id   AS rubro_credito_fiscal_id,
                iva_compras_tax.tax_id              AS iva_compras_tax_id,
                -line.balance * account_currency_table.rate
                    * COALESCE(iva_compras_tax.tax_amount, 0.0) / 100
                                                    AS iva_compras_amount
            """,
            super()._select(),
        )

    @api.model
    def _from(self) -> SQL:
        return SQL(
            """%s
                LEFT JOIN LATERAL (
                    SELECT tax.id AS tax_id, tax.amount AS tax_amount
                    FROM account_move_line_account_tax_rel rel
                    JOIN account_tax tax ON tax.id = rel.account_tax_id
                    JOIN account_tax_group tax_group ON tax_group.id = tax.tax_group_id
                    WHERE rel.account_move_line_id = line.id
                        AND tax_group.group_type = 'vat'
                        AND tax.type_tax_use = 'purchase'
                    LIMIT 1
                ) iva_compras_tax ON TRUE
            """,
            super()._from(),
        )
