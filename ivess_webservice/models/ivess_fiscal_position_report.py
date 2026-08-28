from odoo import api, models

class IvessFiscalPositionReport(models.Model):
    _name = "ivess.fiscal.position.report"
    _description = "Servicio de posiciones fiscales expuesto al middleware Ivess"

    @api.model
    def get_fiscal_positions(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        positions = self.env["account.fiscal.position"].search([])
        return [
            {
                "fiscal_position_id": position.id,
                "name": position.name,
                "afip_code": position.afip_code,
                "supplier_denomination": position.supplier_denomination,
            }
            for position in positions
        ]

