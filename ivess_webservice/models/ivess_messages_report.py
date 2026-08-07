from odoo import api, fields, models, tools

class IvessMessagesReport(models.Model):
    _name = "ivess.messages.report"
    _description = "Vista SQL de mensajes expuesta al middleware Ivess"
    _auto = False

    distribution_id = fields.Many2one("template.delivery.route", readonly=True)
    customer_code = fields.Char(readonly=True)
    partner_message = fields.Text(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ivess_messages_report AS (
                SELECT
                    drl.id AS id,
                    dr.template_delivery_route_id AS distribution_id,
                    drl.customer_code AS customer_code,
                    pdm.message_text AS partner_message
                FROM delivery_route_line drl
                JOIN delivery_route dr
                    ON dr.id = drl.route_id
                    AND dr.state != 'closed'
                JOIN partner_distribution pd
                    ON pd.distribution = dr.template_delivery_route_id
                    AND pd.partner_id = drl.client_id
                JOIN partner_distribution_message pdm
                    ON pdm.partner_distribution_id = pd.id
                    AND pdm.route_id = dr.id
            )
        """)

    @api.model
    def get_messages_report(self, **kwargs):
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
            return {"error": "Se requiere el parámetro distribution."}
        if not isinstance(distribution, str):
            return {
                "error": "El parámetro 'distribution' debe ser una cadena de texto. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        template = self.env["template.delivery.route"].search([("name", "=", distribution)], limit=1)
        if not template:
            return {"error": "No existe ninguna distribución con el código '%s'." % distribution}

        general_messages = self.env["delivery.route.number.message"].search([
            "|",
            ("apply_to_all", "=", True),
            ("delivery_route_number_ids", "in", template.delivery_number_id.id),
        ])

        records = self.search([("distribution_id", "=", template.id)], order="customer_code")
        raw_records = records.read(["customer_code", "partner_message"])

        return {
            "distribution": distribution,
            "general_messages": general_messages.mapped("message_text"),
            "customers": [
                {
                    "customer_code": rec["customer_code"],
                    "partner_message": rec["partner_message"],
                }
                for rec in raw_records
            ],
        }
