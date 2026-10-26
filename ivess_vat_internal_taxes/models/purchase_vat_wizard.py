from odoo import models

from .internal_taxes import get_internal_taxes


class PurchaseVATWizard(models.TransientModel):
    _inherit = 'purchase.vat.wizard'

    def _get_internal_taxes(self):
        # Compra: el impuesto es un débito del asiento, por eso +balance, igual
        # que el neto del resto del reporte (las notas de crédito restan).
        return get_internal_taxes(
            self, ('in_invoice', 'in_refund'), 'purchase', 1
        )

    def run(self):
        # l10n_ar_eynes deja internal_taxes e internal_taxes_refund fijos en 0.
        action = super().run()
        internal_taxes, internal_taxes_refund = self._get_internal_taxes()
        action['data']['internal_taxes'] = internal_taxes
        action['data']['internal_taxes_refund'] = internal_taxes_refund
        return action
