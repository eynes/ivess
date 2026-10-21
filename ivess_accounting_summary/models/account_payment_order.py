from odoo import models


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def _prepare_income_debt_lines(self, lines_type, move_lines):
        res = super()._prepare_income_debt_lines(lines_type, move_lines)
        # La deuda de un comprobante ya resumido vive en el asiento resumen,
        # que no tiene las líneas de gasto/impuesto del comprobante. Se
        # apunta la línea de la OP al comprobante de origen para que la
        # retención (y la base acumulada del mes) se calculen sobre él.
        origin_by_line = {
            line.id: line.x_origin_document_id
            for line in move_lines
            if line.move_id.x_is_summary_entry and line.x_origin_document_id
        }
        for line_data in res:
            origin = origin_by_line.get(line_data["move_line_id"])
            if origin:
                line_data.update({"invoice_id": origin.id, "name": origin.name})
        return res
