from odoo import api, fields, models, tools

class IvessProductsReport(models.Model):
    _name = "ivess.products.report"
    _description = "Vista SQL de productos expuesta al middleware Ivess"
    _auto = False

    default_code         = fields.Char(readonly=True)
    name                 = fields.Char(readonly=True)
    is_promo             = fields.Boolean(readonly=True)    
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
                    COALESCE(pt.name->>'es_AR', pt.name->>'en_US') AS name,
                    pt.is_promo,
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
            "name",
            "is_promo",
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

        promo_tmpl_ids = [r["id"] for r in records if r["is_promo"]]
        boms = self.env["mrp.bom"].search([("product_tmpl_id", "in", promo_tmpl_ids)])
        bom_by_tmpl_id = {bom.product_tmpl_id.id: bom for bom in boms}

        final_records = []
        for r in records:
            components = []
            if r["is_promo"]:
                bom = bom_by_tmpl_id.get(r["id"])
                if bom:
                    for line in bom.bom_line_ids:
                        components.append({
                            "component_id": line.product_id.id,
                            "default_code": line.product_id.default_code,
                            "lst_price": line.product_id.lst_price,
                            "product_qty": line.product_qty,
                            "is_returnable": line.product_id.product_tmpl_id.is_returnable,
                        })
            final_records.append({
                "product_id": r["id"],
                "default_code": r["default_code"],
                "name": r["name"],
                "is_promo": r["is_promo"],
                "allow_free_of_charge": r["allow_free_of_charge"],
                "allows_replacement": r["allows_replacement"],
                "abbreviation": r["abbreviation"],
                "volume": r["volume"],
                "exclude_from_regular": r["exclude_from_regular"],
                "is_returnable": r["is_returnable"],
                "type": r["type"],
                "order": r["order"],
                "tax_amount": r["tax_amount"],
                "components": components,
            })
        return final_records
