from odoo import models

from .internal_taxes import get_internal_taxes


class SaleVATWizard(models.TransientModel):
    _inherit = 'sale.vat.wizard'

    def _get_internal_taxes(self):
        # Venta: el impuesto es un crédito del asiento, por eso -balance, igual
        # que el neto del resto del reporte (las notas de crédito restan).
        return get_internal_taxes(
            self, ('out_invoice', 'out_refund'), 'sale', -1
        )

    def run(self):
        # l10n_ar_eynes deja internal_taxes e internal_taxes_refund fijos en 0.
        # run() ya ajustó las fechas a mes completo: se calcula después.
        action = super().run()
        internal_taxes, internal_taxes_refund = self._get_internal_taxes()
        action['data']['internal_taxes'] = internal_taxes
        action['data']['internal_taxes_refund'] = internal_taxes_refund
        return action
