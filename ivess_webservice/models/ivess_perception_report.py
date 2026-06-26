from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools


class IvessPerceptionReport(models.Model):
    _name = "ivess.perception.report"
    _description = "Vista SQL de percepciones por cliente expuesta al middleware Ivess"
    _auto = False

    customer_code = fields.Char(readonly=True)
    perception_id = fields.Many2one("account.tax", readonly=True)
    tax_minimum = fields.Float(readonly=True)
    percent = fields.Float(readonly=True)
    period = fields.Date(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    rpp.id AS id,
                    rp.customer_code AS customer_code,
                    rpp.perception_id AS perception_id,
                    (
                        SELECT pta.tax_minimum
                        FROM perception_tax_application pta
                        WHERE pta.perception_tax_id = rpp.perception_id
                        LIMIT 1
                    ) AS tax_minimum,
                    rpp.percent AS percent,
                    rpp.period AS period
                FROM res_partner_perception rpp
                JOIN res_partner rp ON rpp.partner_id = rp.id
            )
            """.format(table=self._table)
        )

    @api.model
    def get_perceptions(self, **kwargs):
        allowed_params = {"customer_code", "distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: customer_code, distribution."
                        % ", ".join(sorted(unknown_params))
            }

        customer_code = kwargs.get("customer_code")
        distribution = kwargs.get("distribution")

        if not customer_code and not distribution:
            return {
                "error": "Se requiere al menos uno de los siguientes parámetros: customer_code, distribution."
            }
        if customer_code and distribution:
            return {
                "error": "Los parámetros customer_code y distribution son mutuamente excluyentes. "
                        "Envíe solo uno de ellos."
            }

        for param_name, param_value in [("customer_code", customer_code), ("distribution", distribution)]:
            if param_value is not None and not isinstance(param_value, str):
                return {
                    "error": "El parámetro '%s' debe ser una cadena de texto. "
                            "Tipo recibido: %s." % (param_name, type(param_value).__name__)
                }

        today = fields.Date.today()

        if customer_code:
            if not self.env["res.partner"].search([("customer_code", "=", customer_code)], limit=1):
                return {"error": "No existe ningún cliente con el código '%s'." % customer_code}
            domain = [("customer_code", "=", customer_code)]
        elif distribution:
            template_routes = self.env["template.delivery.route"].search([("name", "=", distribution)])
            if not template_routes:
                return {"error": "No existe ninguna distribución con el código '%s'." % distribution}
            partner_distrs = self.env["partner.distribution"].search([
                ("distribution", "in", template_routes.ids)
            ])
            customer_codes = [c for c in partner_distrs.mapped("partner_id.customer_code") if c]
            domain = [("customer_code", "in", customer_codes)] if customer_codes else [("id", "=", False)]
        lines = self.search(domain, order="customer_code")

        grouped = {}
        for customer, perception in sorted(set(lines.mapped(lambda l: (l.customer_code, l.perception_id))), key=lambda x: x[0]):
            perception_lines = lines.filtered(
                lambda l: l.customer_code == customer and l.perception_id == perception
            )
            match = perception_lines.filtered(
                lambda l: not l.period or (
                    l.period <= today
                    <= (l.period + relativedelta(months=1)) - relativedelta(days=1)
                )
            )
            if match:
                line = match[:1]
                if customer not in grouped:
                    grouped[customer] = {"customer_code": customer, "perceptions": []}
                grouped[customer]["perceptions"].append({
                    "perception_id": (perception.id, perception.display_name),
                    "tax_minimum": line.tax_minimum,
                    "percent": line.percent,
                })

        return list(grouped.values())
