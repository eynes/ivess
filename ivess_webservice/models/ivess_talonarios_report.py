from odoo import api, models

class IvessTalonariosReport(models.Model):
    _name = "ivess.talonarios.report"
    _description = "Servicio de talonarios expuesto al middleware Ivess"

    @api.model
    def get_talonarios(self, **kwargs):
        allowed_params = {"distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: distribution."
                        % ", ".join(sorted(unknown_params))
            }
        distribution = kwargs.get("distribution")
        if not distribution:
            return {
                "error": "Se requiere el parámetro distribution."
            }
        if not type(distribution) is int:
            return {
                "error": "El parámetro 'distribution' debe ser un entero. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        delivery = self.env["delivery.route.number"].search([("number", "=", distribution)], limit=1)
        if not delivery:
            return {"error": "No existe un reparto con el número '%s'." % distribution}

        return {
            "distribution": distribution,
            **delivery._get_booklets_data(),
        }
