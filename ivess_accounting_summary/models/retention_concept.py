from odoo import models


class RetentionConcept(models.Model):
    _inherit = "retention.concept"

    def _get_concept_paid_amount(self, po_line, concept):
        # Mismo criterio que la base de la retención: una deuda resumida se
        # mide sobre el comprobante de origen y no sobre el asiento resumen.
        move_line = po_line.move_line_id
        origin = move_line.x_origin_document_id
        if not (origin and move_line.move_id.x_is_summary_entry):
            return super()._get_concept_paid_amount(po_line, concept)
        concept_lines = (
            self.env["account.tax"]
            ._parse_move_lines(origin)["concept_lines"]
            .filtered(lambda ml: ml.account_id in concept.account_ids)
        )
        amount_with_concept = abs(sum(concept_lines.mapped("balance")))
        percentage_paid = po_line.amount / po_line.amount_original
        return round(amount_with_concept * percentage_paid, 2)
