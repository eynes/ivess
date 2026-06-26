from odoo import api, fields, models, tools


class IvessNonProductiveContainerReport(models.Model):
    _name = "ivess.non.productive.container.report"
    _description = "Vista SQL de envases improductivos expuesta al middleware Ivess"
    _auto = False

    customer_code  = fields.Char(readonly=True)
    default_code   = fields.Char(readonly=True)
    quantity       = fields.Float(readonly=True)
    is_nonproductive = fields.Boolean(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    wc.id            AS id,
                    rp.customer_code AS customer_code,
                    pt.default_code  AS default_code,
                    wc.quantity      AS quantity,
                    wc.is_nonproductive AS is_nonproductive
                FROM water_container wc
                JOIN res_partner      rp ON wc.partner_id = rp.id
                JOIN product_template pt ON wc.product_id = pt.id
                WHERE wc.is_nonproductive = true
            )
            """.format(table=self._table)
        )

    @api.model
    def get_non_productive_containers(self, **kwargs):
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

        if customer_code:
            if not self.env["res.partner"].search([("customer_code", "=", customer_code)], limit=1):
                return {"error": "No existe ningún cliente con el código '%s'." % customer_code}
            domain = [("customer_code", "=", customer_code)]
        else:
            template_routes = self.env["template.delivery.route"].search([("name", "=", distribution)])
            if not template_routes:
                return {"error": "No existe ninguna distribución con el código '%s'." % distribution}
            partner_distrs = self.env["partner.distribution"].search([
                ("distribution", "in", template_routes.ids)
            ])
            customer_codes = [c for c in partner_distrs.mapped("partner_id.customer_code") if c]
            domain = [("customer_code", "in", customer_codes)] if customer_codes else [("id", "=", False)]

        records = self.search(domain, order="customer_code").read(["id", "customer_code", "default_code", "quantity"])
        grouped = {}
        for rec in records:
            code = rec["customer_code"]
            if code not in grouped:
                grouped[code] = {"customer_code": code, "containers": []}
            grouped[code]["containers"].append({
                "product_id": rec["id"],
                "default_code": rec["default_code"],
                "quantity": rec["quantity"],
            })
        return list(grouped.values())
