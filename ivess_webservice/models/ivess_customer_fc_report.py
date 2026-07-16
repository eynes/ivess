from odoo import api, fields, models, tools


class IvessCustomerFcReport(models.Model):
    _name = "ivess.customer.fc.report"
    _description = "Vista SQL de clientes con equipos frio/calor expuesta al middleware Ivess"
    _auto = False

    customer_code = fields.Char(readonly=True)
    lot_id = fields.Char(readonly=True)
    default_code = fields.Char(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    wc.id            AS id,
                    rp.customer_code AS customer_code,
                    sl.name          AS lot_id,
                    pt.default_code  AS default_code
                FROM water_container wc
                JOIN res_partner      rp ON wc.partner_id = rp.id
                JOIN stock_lot        sl ON wc.lot_id = sl.id
                JOIN product_template pt ON wc.product_id = pt.id
                WHERE wc.is_frio_calor = true
            )
            """.format(table=self._table)
        )

    @api.model
    def get_customer_fc_report(self, **kwargs):
        allowed_params = {"distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "El único parámetro aceptado es: distribution."
                        % ", ".join(sorted(unknown_params))
            }

        distribution = kwargs.get("distribution")

        if not distribution:
            return {
                "error": "Se requiere el parámetro 'distribution'."
            }
        if not isinstance(distribution, str):
            return {
                "error": "El parámetro 'distribution' debe ser una cadena de texto. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        template_routes = self.env["template.delivery.route"].search([("name", "=", distribution)])
        if not template_routes:
            return {"error": "No existe ninguna distribución con el código '%s'." % distribution}
        
        partners = self.env["delivery.route.line"].search([
            ("template_route_id", "in", template_routes.ids)
        ]).mapped("client_id")

        customer_codes = []
        for c in partners.mapped("customer_code"):
            if c:
                customer_codes.append(c)
                
        domain = [("customer_code", "in", customer_codes)] if customer_codes else [("id", "=", False)]

        records = self.search(domain, order="customer_code").read(["customer_code", "lot_id", "default_code"])
        grouped = {}
        for rec in records:
            code = rec["customer_code"]
            if code not in grouped:
                grouped[code] = {"customer_code": code, "equipment": []}
            grouped[code]["equipment"].append({
                "lot_id": rec["lot_id"],
                "default_code": rec["default_code"],
            })
        return list(grouped.values())
