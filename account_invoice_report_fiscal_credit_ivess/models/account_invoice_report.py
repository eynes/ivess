from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.logistic_custom_ivess.models.account_invoice_report import (
    AccountInvoiceReport as LogisticAccountInvoiceReport,
)


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    # Mismos valores que account.move.line.fiscal_credit (l10n_ar_eynes): hay
    # un test que verifica que coincidan.
    fiscal_credit = fields.Selection(
        [
            ("direct_taxed", "Directo Gravado"),
            ("direct_exempt", "Directo Exento"),
            ("apport", "Prorrateable"),
        ],
        string="Crédito Fiscal",
        readonly=True,
    )

    # _depends es un atributo de clase plano (no se mergea al heredar, ver
    # odoo/orm/models.py): gana el de la última clase cargada. Como
    # logistic_custom_ivess ya lo reconstruye sobre el del core, se parte del
    # suyo (de ahí la dependencia del módulo) para no perder lo que agrega.
    _depends = {
        **LogisticAccountInvoiceReport._depends,
        "account.move.line": [
            *LogisticAccountInvoiceReport._depends.get("account.move.line", ()),
            "fiscal_credit",
        ],
    }

    @api.model
    def _select(self) -> SQL:
        # fiscal_credit es una columna almacenada de account_move_line (alias
        # "line" en el _from() del core): alcanza con sumarla al SELECT.
        return SQL(
            """%s,
                line.fiscal_credit AS fiscal_credit
            """,
            super()._select(),
        )
