from odoo import api, models

class IvessReplacementReasonReport(models.Model):
    _name = "ivess.replacement.reason.report"
    _description = "Servicio de motivos de recambio expuesto al middleware Ivess"

    @api.model
    def get_replacement_reasons(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        reasons = self.env["replacement.reason"].search([])
        return [
            {
                "replacement_reason_id": reason.id,
                "reason": reason.reason,
                "code": reason.code,
                "sequence": reason.sequence,
            }
            for reason in reasons
        ]

