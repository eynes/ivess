from odoo import fields, models, tools, api

class IvessFcStockInTruck(models.Model):
    _name = "ivess.fc.stock.in.truck"
    _description = "Vista SQL de stock de equipos frio/calor en camión expuesta al middleware Ivess"
    _auto = False

    product_id = fields.Many2one("product.product", readonly=True)
    default_code = fields.Char(readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True)
    lot_id = fields.Many2one("stock.lot", readonly=True)
    inventory_quantity = fields.Float(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    sq.id           AS id,
                    sq.product_id   AS product_id,
                    pt.default_code AS default_code,
                    sq.location_id  AS location_id,
                    sq.lot_id       AS lot_id,
                    sq.quantity     AS inventory_quantity
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE pt.is_frio_calor = TRUE
            )
            """.format(table=self._table)
        )

    @api.model
    def get_fc_stock_in_truck(self, **kwargs):
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
                "error": "Se requiere el parámetro distribution."
            }
        if not isinstance(distribution, int):
            return {
                "error": "El parámetro 'distribution' debe ser un entero. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        delivery_number = self.env['delivery.route.number'].search([('number', '=', distribution)], limit=1)
        if not delivery_number:
            return {"error": "No existe un reparto con el código '%s'." % distribution}
        if not delivery_number.location_id:
            return {"error": "El reparto '%s' no tiene una ubicación de stock asignada." % distribution}

        records = self.search([('location_id', '=', delivery_number.location_id.id)])
        raw_records = records.read(['default_code', 'lot_id', 'inventory_quantity'])

        grouped = {}
        for rec in raw_records:
            code = rec['default_code']
            lot_id = rec['lot_id'][1] if rec['lot_id'] else None
            key = (code, lot_id)
            if key not in grouped:
                grouped[key] = {'default_code': code, 'lot_id': lot_id, 'quantity': 0.0}
            grouped[key]['quantity'] += rec['inventory_quantity']

        return list(grouped.values())