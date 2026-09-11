from odoo import api, models


class IvessProductsReport(models.Model):
    _name = "ivess.products.report"
    _description = "Servicio de productos expuesto al middleware Ivess"

    @api.model
    def get_products(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}

        products = self.env["product.template"].with_context(lang="es_AR").search(
            [("show_in_app", "=", True)], order="id"
        )

        promo_products = products.filtered("is_promo")
        boms = self.env["mrp.bom"].search([("product_tmpl_id", "in", promo_products.ids)])
        bom_by_tmpl_id = {bom.product_tmpl_id.id: bom for bom in boms}

        final_records = []
        for product in products:
            if product.authorize_for_technical_service:
                final_records.append({
                    "product_id": product.id,
                    "name": product.name,
                    "is_service": product.authorize_for_technical_service,
                })
                continue

            components = []
            if product.is_promo:
                bom = bom_by_tmpl_id.get(product.id)
                if bom:
                    for line in bom.bom_line_ids:
                        components.append({
                            "component_id": line.product_id.id,
                            "default_code": line.product_id.default_code,
                            "lst_price": line.product_id.lst_price,
                            "product_qty": line.product_qty,
                            "is_returnable": line.product_id.product_tmpl_id.is_returnable,
                        })

            tax = product.taxes_id.filtered(lambda t: t.group_type == "internals")[:1]

            final_records.append({
                "product_id": product.id,
                "default_code": product.default_code,
                "name": product.name,
                "is_promo": product.is_promo,
                "allow_free_of_charge": product.allow_free_of_charge,
                "allows_replacement": product.allows_replacement,
                "abbreviation": product.abbreviation,
                "volume": product.volume,
                "exclude_from_regular": product.exclude_from_regular,
                "is_returnable": product.is_returnable,
                "type": product.type,
                "order": product.order,
                "tax_amount": tax.amount if tax else 0,
                "components": components,
            })
        return final_records
