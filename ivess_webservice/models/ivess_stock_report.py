from odoo import api, fields, models, tools


class IvessStockReport(models.Model):
    _name = "ivess.stock.report"
    _description = "Vista SQL de stock de envases expuesta al middleware Ivess"
    _auto = False

    product_id = fields.Many2one("product.product", readonly=True)
    default_code = fields.Char(readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True)
    inventory_quantity = fields.Float(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    sq.id           AS id,
                    sq.product_id   AS product_id,
                    pp.default_code AS default_code,
                    sq.location_id  AS location_id,
                    sq.quantity     AS inventory_quantity
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
            )
            """.format(table=self._table)
        )

    @api.model
    def get_stock(self, **kwargs):
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
        if not isinstance(distribution, str):
            return {
                "error": "El parámetro 'distribution' debe ser una cadena de texto. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        template_routes = self.env["template.delivery.route"].search([("name", "=", distribution)])
        if not template_routes:
            return {"error": "No existe ninguna distribución con el código '%s'." % distribution}

        location_ids = template_routes.mapped("delivery_number_id.location_id").ids
        domain = [("location_id", "in", location_ids)] if location_ids else [("id", "=", False)]

        records = self.search(domain).read(["product_id", "default_code", "inventory_quantity"])
        grouped = {}
        for rec in records:
            product_id = rec["product_id"][0] if rec["product_id"] else False
            if product_id not in grouped:
                grouped[product_id] = {
                    "product_id": product_id,
                    "default_code": rec["default_code"],
                    "quantity": 0.0,
                }
            grouped[product_id]["quantity"] += rec["inventory_quantity"]
        return list(grouped.values())
