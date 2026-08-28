from odoo import api, models

class IvessLocalitiesReport(models.Model):
    _name = "ivess.localities.report"
    _description = "Servicio de localidades expuesto al middleware Ivess"

    @api.model
    def get_localities(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        localities = self.env["res.city"].search([], order="id")
        return [
            {"locality_id": locality.id, "name": locality.name, "zip_code": locality.zipcode}
            for locality in localities
        ]
