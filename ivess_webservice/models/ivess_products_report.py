from odoo import api, fields, models, tools

class IvessProductsReport(models.Model):
    _name = "ivess.products.report"
    _description = "Vista SQL de productos expuesta al middleware Ivess"
    _auto = False

    default_code         = fields.Char(readonly=True)
    allow_free_of_charge = fields.Boolean(readonly=True)
    allows_replacement   = fields.Boolean(readonly=True)
    abbreviation         = fields.Char(readonly=True)
    volume               = fields.Float(readonly=True)
    exclude_from_regular = fields.Boolean(readonly=True)
    is_returnable        = fields.Boolean(readonly=True)
    type                 = fields.Char(readonly=True)
    order                = fields.Integer(readonly=True)
    tax_amount           = fields.Float(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    pt.id,
                    pt.default_code,
                    pt.allow_free_of_charge,
                    pt.allows_replacement,
                    pt.abbreviation,
                    pt.volume,
                    pt.exclude_from_regular,
                    pt.is_returnable,
                    pt.type,
                    pt."order",
                    COALESCE((
                        SELECT at.amount
                        FROM product_taxes_rel ptr
                        JOIN account_tax at ON at.id = ptr.tax_id
                        JOIN account_tax_group atg ON atg.id = at.tax_group_id
                        WHERE ptr.prod_id = pt.id
                            AND atg.group_type = 'internals'
                        LIMIT 1
                    ), 0) AS tax_amount
                FROM product_template pt
                WHERE pt.show_in_app = True
            )
            """.format(table=self._table)
        )

    @api.model
    def get_products(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        records = self.search([]).read([
            "id",
            "default_code",
            "allow_free_of_charge",
            "allows_replacement",
            "abbreviation",
            "volume",
            "exclude_from_regular",
            "is_returnable",
            "type",
            "order",
            "tax_amount",
        ])
        final_records = []
        for r in records:
            final_records.append({
                "product_id": r["id"],
                "default_code": r["default_code"],
                "allow_free_of_charge": r["allow_free_of_charge"],
                "allows_replacement": r["allows_replacement"],
                "abbreviation": r["abbreviation"],
                "volume": r["volume"],
                "exclude_from_regular": r["exclude_from_regular"],
                "is_returnable": r["is_returnable"],
                "type": r["type"],
                "order": r["order"],
                "tax_amount": r["tax_amount"],
            })
        return final_records
