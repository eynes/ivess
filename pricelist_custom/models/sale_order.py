from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends(
        'delivery_route_id',
        'delivery_route_id.template_delivery_route_id',
        'delivery_route_id.template_delivery_route_id.pricelist_id',
        'partner_id.specific_property_product_pricelist',
        'partner_id.distribution',
        'partner_id.distribution.pricelist_id',
    )
    def _compute_pricelist_id(self):
        """
        Extiende el cálculo nativo de la lista de precios:
        - Prioridad C: lista de la ruta de reparto del pedido.
        - Prioridad D: lista de la distribución del cliente.
        Ambas aplican solo si el cliente no tiene lista asignada explícitamente
        (specific_property_product_pricelist vacío).
        """
        super()._compute_pricelist_id()
        for order in self:
            if order.partner_id.property_product_pricelist:
                continue
            route_pricelist = (
                order.delivery_route_id
                .template_delivery_route_id
                .pricelist_id
            )
            if route_pricelist:
                order.pricelist_id = route_pricelist
                continue
            distribution_pricelist = order.partner_id.distribution.pricelist_id
            if distribution_pricelist:
                order.pricelist_id = distribution_pricelist


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.depends(
        'product_id',
        'order_id.pricelist_id',
        'order_id.delivery_route_id.template_delivery_route_id.pricelist_id',
        'order_id.partner_id.customer_discount_percentage',
        'order_id.partner_id.distribution.pricelist_id',
        'order_id.partner_id.special_price_ids',
        'order_id.partner_id.special_price_ids.product_id',
    )
    def _compute_discount(self):
        super()._compute_discount()
        for line in self:
            if not line.product_id or line.display_type:
                continue
            partner = line.order_id.partner_id
            special = line._get_partner_special_price()
            if special:
                line.discount = 0.0
            elif line._is_using_route_pricelist():
                line.discount = 0.0
            elif line._has_product_rule_in_pricelist(line.order_id.pricelist_id):
                line.discount = partner.customer_discount_percentage or 0.0
            else:
                line.discount = 0.0

    def _reset_price_unit(self):
        super()._reset_price_unit()
        partner = self.order_id.partner_id
        special = self._get_partner_special_price()
        if special:
            self.price_unit = special.special_price
            self.technical_price_unit = special.special_price
            self.discount = 0.0
        elif self._is_using_route_pricelist():
            self.discount = 0.0
        elif self._has_product_rule_in_pricelist(self.order_id.pricelist_id):
            self.discount = partner.customer_discount_percentage or 0.0
        else:
            route_pricelist = self._get_route_pricelist()
            if route_pricelist:
                price = route_pricelist._get_product_price(
                    self.product_id,
                    self.product_uom_qty or 1.0,
                    currency=self.order_id.currency_id,
                    date=self.order_id.date_order,
                )
                self.price_unit = price
                self.technical_price_unit = price
            self.discount = 0.0

    def _is_using_route_pricelist(self):
        """True si el pedido está usando la lista de precios del reparto como lista activa."""
        route_pricelist = self._get_route_pricelist()
        return bool(route_pricelist and self.order_id.pricelist_id == route_pricelist)

    def _get_route_pricelist(self):
        # Obtiene la lista de precios de:
        # 1. Orden de venta -> Ruta de reparto -> Recorrido de reparto -> Lista de precios
        # 2. Else Orden de venta -> Partner -> Distribución (Recorrido de reparto) -> Lista de reparto
        order = self.order_id
        route_pricelist = (
            order.delivery_route_id
            .template_delivery_route_id
            .pricelist_id
        )
        return route_pricelist or order.partner_id.distribution.pricelist_id

    def _has_product_rule_in_pricelist(self, pricelist):
        """True si la lista tiene una regla específica para este producto (variante, template o categoría)."""
        if not pricelist or not self.product_id:
            return False
        product = self.product_id
        product_tmpl = product.product_tmpl_id
        categ_ids = set()
        categ = product_tmpl.categ_id
        while categ:
            categ_ids.add(categ.id)
            categ = categ.parent_id
        return bool(pricelist.item_ids.filtered(
            lambda item: (
                (item.applied_on == '0_product_variant' and item.product_id == product) or
                (item.applied_on == '1_product' and item.product_tmpl_id == product_tmpl) or
                (item.applied_on == '2_product_category' and item.categ_id.id in categ_ids)
            )
        ))

    def _get_partner_special_price(self):
        """Devuelve el primer precio especial del cliente para este producto, o False."""
        self.ensure_one()
        partner = self.order_id.partner_id
        if not partner or not self.product_id:
            return False
        return partner.special_price_ids.filtered(
            lambda sp: sp.product_id == self.product_id
        )[:1]
