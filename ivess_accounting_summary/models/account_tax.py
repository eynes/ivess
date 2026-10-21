from odoo import models


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _compute_base_retention(self, payment, move_line, *args, **kwargs):
        # El cálculo solo usa move_line.move_id para leer las líneas del
        # comprobante. Con una deuda resumida eso es el asiento resumen (sin
        # líneas de gasto), y la retención daba 0 aunque la línea de deuda
        # viniera bien. Se usa el comprobante de origen.
        origin = move_line.x_origin_document_id
        if origin and move_line.move_id.x_is_summary_entry and origin.line_ids:
            move_line = origin.line_ids[:1]
        return super()._compute_base_retention(payment, move_line, *args, **kwargs)
