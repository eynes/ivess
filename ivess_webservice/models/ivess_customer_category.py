from odoo import api, models


class IvessCustomerCategory(models.Model):
    _name = "ivess.customer.category"
    _description = "Servicio de categorías de clientes expuesto al middleware Ivess"

    @api.model
    def get_customer_categories(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        categories = self.env["registration.channel"].search([])
        return [
            {"customer_category_id": categorie.id, "name": categorie.name}
            for categorie in categories
        ]
