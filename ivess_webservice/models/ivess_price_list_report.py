from odoo import api, models


class IvessPriceListReport(models.Model):
    _name = "ivess.price.list.report"
    _description = "Lista de precios expuesta al middleware Ivess"

    @api.model
    def get_price_list(self, **kwargs):
        allowed_params = {"distribution", "customer_code"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: distribution, customer_code."
                        % ", ".join(sorted(unknown_params))
            }

        distribution = kwargs.get("distribution")
        customer_code = kwargs.get("customer_code")

        if not distribution and not customer_code:
            return {"error": "Se requiere al menos uno de los parámetros: distribution, customer_code."}
        if distribution and customer_code:
            return {"error": "Los parámetros distribution y customer_code son mutuamente excluyentes."}

        for name, value in [("distribution", distribution), ("customer_code", customer_code)]:
            if value is not None and not isinstance(value, str):
                return {
                    "error": "El parámetro '%s' debe ser una cadena de texto. Tipo recibido: %s."
                            % (name, type(value).__name__)
                }

        if customer_code:
            return self._get_by_customer(customer_code)
        return self._get_by_distribution(distribution)

    # ------------------------------------------------------------------
    # Handlers principales
    # ------------------------------------------------------------------

    def _get_by_distribution(self, distribution_name):
        distribution = self.env["template.delivery.route"].search(
            [("name", "=", distribution_name)], limit=1
        )
        if not distribution:
            return {"error": "No existe ninguna distribución con el código '%s'." % distribution_name}

        dist_pricelist = distribution.pricelist_id
        if not dist_pricelist:
            return {"error": "La distribución '%s' no tiene lista de precios asignada." % distribution_name}

        dist_products = self._get_pricelist_products(dist_pricelist)

        base_prices = {}
        for product in dist_products:
            if not product.default_code:
                continue
            base_prices[product.default_code] = dist_pricelist._get_product_price(product, 1.0)

        partners = self.env["res.partner"].search([
            ("distribution", "=", distribution.id),
            ("customer_code", "!=", False),
            ("active", "=", True),
        ])

        clients = []
        for partner in partners:
            overrides = self._get_partner_overrides(partner, dist_products, base_prices)
            if overrides:
                clients.append({
                    "customer_code": partner.customer_code,
                    "products": overrides,
                })

        return {
            "distribution": distribution_name,
            "products": [
                {"default_code": code, "price": price}
                for code, price in base_prices.items()
            ],
            "clients": clients,
        }

    def _get_by_customer(self, customer_code):
        partner = self.env["res.partner"].search(
            [("customer_code", "=", customer_code)], limit=1
        )
        if not partner:
            return {"error": "No existe ningún cliente con el código '%s'." % customer_code}

        distributions = partner.distribution
        for dist_line in partner.distributions_ids:
            distributions |= dist_line.distribution

        if not distributions or len(distributions) > 1:
            return {
                "customer_code": customer_code,
                "distributions": [],
                "client_products": self._get_partner_overrides(
                    partner, self.env["product.product"], {}
                ),
            }

        dist_entries = []
        for distribution in distributions:
            dist_pricelist = distribution.pricelist_id
            dist_products = (
                self._get_pricelist_products(dist_pricelist) if dist_pricelist
                else self.env["product.product"]
            )
            base_prices = {}
            for product in dist_products:
                if not product.default_code:
                    continue
                base_prices[product.default_code] = dist_pricelist._get_product_price(product, 1.0)

            dist_entries.append({
                "distribution": distribution.name,
                "products": [
                    {"default_code": code, "price": price}
                    for code, price in base_prices.items()
                ],
                "client_products": self._get_partner_overrides(partner, dist_products, base_prices),
            })

        return {
            "customer_code": customer_code,
            "distributions": dist_entries,
        }

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _get_partner_overrides(self, partner, dist_products, base_prices):
        partner_pricelist = partner.property_product_pricelist
        pricelist_products = (
            self._get_pricelist_products(partner_pricelist) if partner_pricelist
            else self.env["product.product"]
        )

        all_products = self.env["product.product"].browse(
            set(dist_products.ids) | set(pricelist_products.ids) |
            {sp.product_id.id for sp in partner.special_price_ids if sp.product_id}
        )

        overrides = []
        seen_codes = set()
        for product in all_products:
            code = product.default_code
            if not code or code in seen_codes:
                continue

            special = partner.special_price_ids.filtered(
                lambda sp, p=product: sp.product_id == p
            )[:1]
            if special:
                price = special.special_price
            elif partner_pricelist and self._has_product_rule_in_pricelist(product, partner_pricelist):
                price = partner_pricelist._get_product_price(product, 1.0)
            else:
                continue

            in_dist = product in dist_products
            if in_dist and price == base_prices.get(code, 0.0):
                continue

            overrides.append({"default_code": code, "price": price})
            seen_codes.add(code)

        return overrides

    def _get_pricelist_products(self, pricelist):
        products = self.env["product.product"]
        for item in pricelist.item_ids:
            if item.applied_on == "0_product_variant":
                products |= item.product_id
            elif item.applied_on == "1_product":
                products |= item.product_tmpl_id.product_variant_ids
            elif item.applied_on == "2_product_category":
                products |= self.env["product.product"].search([
                    ("categ_id", "child_of", item.categ_id.id),
                    ("active", "=", True),
                ])
            elif item.applied_on == "3_global":
                products |= self.env["product.product"].search([("active", "=", True)])
        return products

    def _has_product_rule_in_pricelist(self, product, pricelist):
        product_tmpl = product.product_tmpl_id
        categ_ids = set()
        categ = product_tmpl.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return bool(pricelist.item_ids.filtered(
            lambda item: (
                (item.applied_on == "0_product_variant" and item.product_id == product) or
                (item.applied_on == "1_product" and item.product_tmpl_id == product_tmpl) or
                (item.applied_on == "2_product_category" and item.categ_id.id in categ_ids)
            )
        ))
