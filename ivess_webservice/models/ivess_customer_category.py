from odoo import api, fields, models, tools


class IvessCustomerCategory(models.Model):
    _name = "ivess.customer.category"
    _description = "Vista SQL de categorías de clientes expuesta al middleware Ivess"
    _auto = False

    name = fields.Char(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    id,
                    name
                FROM registration_channel
            )
            """.format(table=self._table)
        )

    @api.model
    def get_customer_categories(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        records = self.search([])
        return records.read(["name"])