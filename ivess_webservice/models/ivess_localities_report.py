from odoo import api, fields, models, tools

class IvessLocalitiesReport(models.Model):
    _name = "ivess.localities.report"
    _description = "Vista SQL de localidades expuesta al middleware Ivess" 
    _auto = False

    name = fields.Char(translate=True, readonly=True)
    zipcode = fields.Char(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    id,
                    name,
                    zipcode
                FROM res_city
            )
            """.format(table=self._table) 
        )

    @api.model
    def get_localities(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        records = self.search([]).read(["id", "name", "zipcode"])
        final_records = []
        for r in records:
            final_records.append({
                "locality_id": r["id"],
                "name": r["name"],
                "zip_code": r["zipcode"],
            })
        return final_records