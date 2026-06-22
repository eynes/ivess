from datetime import timedelta
from odoo import api, fields, models, tools

class IvessLimitFreeOfChargeReport(models.Model):
    _name = "ivess.limit.free.of.charge.report"
    _description = "Vista SQL de  Topes sin cargo expuesta al middleware Ivess"
    _auto = False

    default_code = fields.Char(readonly=True)
    monthly_limit_free_of_charge = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ivess_limit_free_of_charge_report AS (
                SELECT
                id,
                default_code,
                monthly_limit_free_of_charge
                FROM product_template
            )
        """)

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

        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=31)).replace(day=1)

        order_domain = [
            ('state', 'in', ('sale', 'done')),
            ('date_order', '>=', fields.Datetime.to_datetime(month_start)),
            ('date_order', '<', fields.Datetime.to_datetime(next_month)),
        ]

        if distribution:
            template_routes = self.env['template.delivery.route'].search([('name', '=', distribution)])
            if not template_routes:
                return {'error': "No existe ninguna distribución con el nombre '%s'." % distribution}
            delivery_routes = self.env['delivery.route'].search([
                ('template_delivery_route_id', 'in', template_routes.ids)
            ])
            order_domain.append(('delivery_route_id', 'in', delivery_routes.ids))
        else:
            partner = self.env['res.partner'].search([('customer_code', '=', customer_code)], limit=1)
            if not partner:
                return {'error': "No existe ningún cliente con el código '%s'." % customer_code}
            order_domain.append(('partner_id', '=', partner.id))

        sale_orders = self.env['sale.order'].search(order_domain)
        free_lines = sale_orders.order_line.filtered(lambda l: l.free_of_charge)

        consumed_by_tmpl = {}
        for line in free_lines:
            tmpl_id = line.product_id.product_tmpl_id.id
            consumed_by_tmpl[tmpl_id] = consumed_by_tmpl.get(tmpl_id, 0.0) + line.product_uom_qty

        products = self.env['product.template'].search([('allow_free_of_charge', '=', True)])

        return [
            {
                'product_id': product.id,
                'default_code': product.default_code,
                'monthly_limit_free_of_charge': product.monthly_limit_free_of_charge,
                'consumed_qty': consumed_by_tmpl.get(product.id, 0.0),
            }
            for product in products
        ]
