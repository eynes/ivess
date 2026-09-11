from odoo import api, models

class IvessNoPurchaseReasonReport(models.Model):
    _name = "ivess.no.purchase.reason.report"
    _description = "Servicio de motivos de no compra expuesto al middleware Ivess"

    @api.model
    def get_no_purchase_reasons(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        reasons = self.env["no.purchase.reason"].search([])
        return [
            {
                "no_purchase_reason_id": reason.id,
                "reason": reason.reason,
                "code": reason.code,
                "order": reason.order,
            }
            for reason in reasons
        ]