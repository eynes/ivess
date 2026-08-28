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

        remittance_sequence = delivery.remittance_sequence_id
        collection_journal = delivery.collection_journal_id
        repair_order_sequence = delivery.repair_order_sequence_id

        return {
            "distribution": distribution,
            "rem_next_number": remittance_sequence.number_next_actual if remittance_sequence else None,
            "rem_prefix": remittance_sequence.prefix if remittance_sequence else None,
            "rec_next_number": collection_journal.sequence_number_next if collection_journal else None,
            "rec_prefix": collection_journal.code if collection_journal else None,
            "or_next_number": repair_order_sequence.number_next_actual if repair_order_sequence else None,
            "or_prefix": repair_order_sequence.prefix if repair_order_sequence else None,
        }