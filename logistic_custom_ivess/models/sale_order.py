from odoo import models, api, fields
from datetime import date


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_route_id = fields.Many2one(
        'delivery.route', 
        string="Delivery Route"
    )

    def write(self, vals):
        previous_routes_by_order = {
            order.id: order.delivery_route_id.id
        for order in self
        }
        res = super().write(vals)
        if 'delivery_route_id' in vals:
            self.assign_route_to_invoices(vals, previous_routes_by_order)
        return res
    
    def assign_route_to_invoices(self, vals, previous_routes_by_order):
        """
            Sincroniza la ruta de reparto (delivery_route_id) del pedido de venta (sale.order)
            con las facturas relacionadas (account.move) que tengan como origen dicho pedido.
            Esta función:
            - Agrega la nueva ruta de reparto en las facturas si aún no está asignada.
            - Reemplaza la ruta anterior si fue modificada.
            - Elimina la ruta de las facturas si fue eliminada del pedido de venta.
            Las facturas se identifican por el campo 'invoice_origin', que puede contener
            uno o más nombres de pedidos separados por comas.
            Aplica solo a los registros de account.move cuyo tipo (move_type) sea:
            'out_invoice' (Factura de cliente), 
            'out_refund' (Nota de crédito), o 
            'out_receipt' (Nota de débito).
        """
        for order in self:
            new_route_id = vals.get('delivery_route_id')  # Puede ser False o un ID
            previous_route_id = previous_routes_by_order.get(order.id)
            order_name = order.name

            moves = self.env['account.move'].search([
                ('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt')),
                ('invoice_origin', '!=', False),
            ])

            # Filtramos los que contengan el nombre de este pedido
            related_moves = moves.filtered(
                lambda m: order_name in [x.strip() for x in m.invoice_origin.split(',')]
            )

            for move in related_moves:
                # CASO 1: Se quitó la ruta de reparto, eliminar la anterior si existe
                if not new_route_id and previous_route_id:
                    move.delivery_route_ids = move.delivery_route_ids.filtered(
                        lambda r: r.id != previous_route_id
                    )

                # CASO 2: Se reemplazó por una nueva ruta
                elif new_route_id:
                    # Si hay una ruta anterior distinta, eliminarla
                    if previous_route_id and previous_route_id != new_route_id:
                        move.delivery_route_ids = move.delivery_route_ids.filtered(
                            lambda r: r.id != previous_route_id
                        )
                    # Agregar la nueva si no está
                    if new_route_id not in move.delivery_route_ids.ids:
                        move.delivery_route_ids = [(4, new_route_id)]
    
    def _action_cancel(self):
        res = super()._action_cancel()
        for order in self:
            total_liters = order._calculate_total_liters()
            if total_liters:
                month, year = order._get_month_year_from_date()
                order.update_or_delete_partner_water_consumption(month, year, total_liters)
        return res

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            total_liters = order._calculate_total_liters()
            if total_liters:
                month, year = order._get_month_year_from_date()
                order._update_or_create_partner_water_consumption(month, year, total_liters)
        return res

    def _calculate_total_liters(self):
        """Calculate total liters for this sale order based on products' liter_quantity."""
        self.ensure_one()
        total = 0.0
        for line in self.order_line:
            liters_per_unit = line.product_id.product_tmpl_id.liter_quantity
            if liters_per_unit:
                total += line.product_uom_qty * liters_per_unit
        return total

    def _get_month_year_from_date(self):
        """Return month and year from sale order's confirmation date."""
        self.ensure_one()
        order_date = self.date_order.date()
        return order_date.month, order_date.year

    def _update_or_create_partner_water_consumption(self, month, year, liters):
        """Create or update the water consumption record for the partner."""
        self.ensure_one()
        WaterConsumption = self.env['res.partner.water.consumption']
        record = WaterConsumption.search([
            ('partner_id', '=', self.partner_id.id),
            ('month', '=', month),
            ('year', '=', year)
        ], limit=1)
        if record:
            record.consumption_liters += liters
        else:
            WaterConsumption.create({
                'partner_id': self.partner_id.id,
                'month': month,
                'year': year,
                'consumption_liters': liters,
            })
    
    def update_or_delete_partner_water_consumption(self, month, year, liters):
        self.ensure_one()
        WaterConsumption = self.env['res.partner.water.consumption']
        record = WaterConsumption.search([
            ('partner_id', '=', self.partner_id.id),
            ('month', '=', month),
            ('year', '=', year)
        ], limit=1)
        if record:
            if record.consumption_liters <= liters:
                record.unlink()
            else:
                record.consumption_liters -= liters


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    replacement_reason_id = fields.Many2one(
        'replacement.reason',
        string="Replacement Reason",
        tracking=True,
    )
