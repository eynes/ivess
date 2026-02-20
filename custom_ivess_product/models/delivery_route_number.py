from odoo import models, fields, api, _


class DeliveryRouteNumber(models.Model):
    _name = 'delivery.route.number'
    _description = 'Delivery Route Number'
    _rec_name = 'number'
    _sql_constraints = [
        (
            'unique_delivery_route_number',  
            'UNIQUE(number)',               
            _('The delivery route number must be unique.')
        )
    ]

    def _get_default_number(self):
        last_route = self.search([], order='number desc', limit=1)
        return last_route.number + 1 if last_route else 1

    number = fields.Integer(
        string="Number",
        default=_get_default_number
    )
    #truck_id = fields.Many2one(
    #    'fleet.truck',
    #    string='Truck License Plate',
    #)
    allow_price_editing = fields.Boolean(string="Allow Price Editing")
    allow_free_of_charge = fields.Boolean(string="Allow Free Of Charge")
    allow_reordering = fields.Boolean(
        string="Enable Reordering",
        help="Enables reordering of customers in delivery routes.",
    )
    allow_previous_price = fields.Boolean(string='Allow Previous Price')
    allow_sale_without_stock = fields.Boolean(string='Allow sale without stock')
    allow_closing_with_rake = fields.Boolean(string='Allow closing with rake')
    is_cold_hot_delivery = fields.Boolean(string="Is cold hot delivery")
    allow_cash_sale = fields.Boolean(
        string='Allow Cash Sale',
        required=True,
        tracking=True,
        default=False,
        help="If checked, this delivery number permits sales paid in cash."
    )
    allow_manual_address = fields.Boolean(
        string='Allow Manual Address',
        default=True,
        help="If checked, customers can enter a manual address for this delivery."
    )


