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
        'order_id.partner_id.customer_discount_percentage',
        'order_id.partner_id.special_price_ids',
        'order_id.partner_id.special_price_ids.product_id',
    )
    def _compute_discount(self):
        """
        Extiende el cálculo nativo del descuento:
        - Prioridad A: si se aplicó precio especial, el descuento se fuerza a 0.
        - Prioridad B: si no hay precio especial, se inyecta el % de descuento del cliente.
        """
        super()._compute_discount()
        for line in self:
            if not line.product_id or line.display_type:
                continue
            partner = line.order_id.partner_id
            special = line._get_partner_special_price()
            if special:
                line.discount = 0.0
            elif partner.customer_discount_percentage:
                line.discount = partner.customer_discount_percentage

    def _reset_price_unit(self):
        super()._reset_price_unit()
        special = self._get_partner_special_price()
        if special:
            self.price_unit = special.special_price
            self.technical_price_unit = special.special_price
            self.discount = 0.0
        elif self.order_id.partner_id.customer_discount_percentage:
            self.discount = self.order_id.partner_id.customer_discount_percentage

    def _get_partner_special_price(self):
        """Devuelve el primer precio especial del cliente para este producto, o False."""
        self.ensure_one()
        partner = self.order_id.partner_id
        if not partner or not self.product_id:
            return False
        return partner.special_price_ids.filtered(
            lambda sp: sp.product_id == self.product_id
        )[:1]
