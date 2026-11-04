from datetime import datetime, time, timedelta
import pytz
from odoo import api, models

class IvessLimitFreeOfChargeReport(models.Model):
    _name = "ivess.limit.free.of.charge.report"
    _description = "Servicio de topes sin cargo expuesto al middleware Ivess"

    @api.model
    def get_limit_free_of_charge(self, **kwargs):
        allowed_params = {'distribution', 'customer_code'}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                'error': 'Parámetros no reconocidos: %s. '
                        'Los parámetros aceptados son: distribution, customer_code.'
                        % ', '.join(sorted(unknown_params))
            }

        distribution = kwargs.get('distribution')
        customer_code = kwargs.get('customer_code')

        if not distribution and not customer_code:
            return {
                'error': 'Se requiere al menos uno de los siguientes parámetros: distribution, customer_code.'
            }
        if distribution and customer_code:
            return {
                'error': 'Los parámetros distribution y customer_code son mutuamente excluyentes. '
                        'Envíe solo uno de ellos.'
            }

        for param_name, param_value in [('distribution', distribution), ('customer_code', customer_code)]:
            if param_value is not None and not isinstance(param_value, str):
                return {
                    'error': "El parámetro '%s' debe ser una cadena de texto. "
                            "Tipo recibido: %s." % (param_name, type(param_value).__name__)
                }

        tz = pytz.timezone(
            self.env.context.get('tz') or self.env.user.tz or 'America/Argentina/Buenos_Aires'
        )
        today = datetime.now(tz).date()
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=31)).replace(day=1)

        def _local_midnight_utc(day):
            """
            Medianoche de `day` en hora local, expresada en UTC (como guarda Odoo date_order).
            Evita que los pedidos de las últimas/primeras horas del mes caigan en el mes equivocado.
            """
            midnight = datetime.combine(day, time.min)
            local_midnight = tz.localize(midnight)
            utc_midnight = local_midnight.astimezone(pytz.utc)
            return utc_midnight.replace(tzinfo=None)

        order_domain = [
            ('state', 'in', ('sale', 'done')),
            ('date_order', '>=', _local_midnight_utc(month_start)),
            ('date_order', '<', _local_midnight_utc(next_month)),
        ]

        partner = None
        if distribution:
            template_routes = self.env['template.delivery.route'].search([('name', '=', distribution)])
            if not template_routes:
                return {'error': "No existe ninguna distribución con el nombre '%s'." % distribution}
            order_domain.append(
                ('delivery_route_id.template_delivery_route_id', 'in', template_routes.ids)
            )
        else:
            partner = self.env['res.partner'].search([('customer_code', '=', customer_code)], limit=1)
            if not partner:
                return {'error': "No existe ningún cliente con el código '%s'." % customer_code}
            order_domain.append(('partner_id', '=', partner.id))

        sale_orders = self.env['sale.order'].search(order_domain)
        free_lines = sale_orders.order_line.filtered(lambda l: l.free_of_charge)

        # {id_template: {id_cliente: cantidad consumida}}
        consumed_by_tmpl = {}
        # {id_cliente: customer_code}
        partner_codes = {}

        for line in free_lines:
            tmpl_id = line.product_id.product_tmpl_id.id
            line_partner = line.order_id.partner_id

            if tmpl_id not in consumed_by_tmpl:
                consumed_by_tmpl[tmpl_id] = {}

            already_consumed = consumed_by_tmpl[tmpl_id].get(line_partner.id, 0.0)
            consumed_by_tmpl[tmpl_id][line_partner.id] = already_consumed + line.product_uom_qty

            partner_codes[line_partner.id] = line_partner.customer_code

        # Productos marcados como "permitidos sin cargo" en el catálogo, y productos consumidos en el período (aunque no estén marcados como permitidos)
        catalog_products = self.env['product.template'].search([('allow_free_of_charge', '=', True)])
        consumed_products = self.env['product.template'].browse(list(consumed_by_tmpl))

        # Unión de ambos, sin repetidos
        products = (catalog_products | consumed_products).sorted()

        result = []
        for product in products:
            product_data = {
                'product_id': product.id,
                'default_code': product.default_code,
                'monthly_limit_free_of_charge': product.monthly_limit_free_of_charge,
            }
            # {id_cliente: cantidad consumida} de este producto (vacío si nadie lo consumió)
            consumed_by_partner = consumed_by_tmpl.get(product.id, {})

            if partner:
                # Consulta por cliente: una fila por producto, aunque no haya consumo
                result.append({
                    'customer_code': partner.customer_code,
                    **product_data,
                    'consumed_qty': consumed_by_partner.get(partner.id, 0.0),
                })
            elif consumed_by_partner:
                # Consulta por reparto, producto con consumo: una fila por cliente
                for partner_id, consumed_qty in consumed_by_partner.items():
                    result.append({
                        'customer_code': partner_codes[partner_id],
                        **product_data,
                        'consumed_qty': consumed_qty,
                    })
            else:
                # Consulta por reparto, producto sin consumo: una fila sin cliente
                result.append({
                    'customer_code': False,
                    **product_data,
                    'consumed_qty': 0.0,
                })

        return result
