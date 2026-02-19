from odoo import models, fields, api

day_mapping = {
    'monday': 'A',
    'tuesday': 'B',
    'wednesday': 'C',
    'thursday': 'D',
    'friday': 'E',
    'saturday': 'F',
    'sunday': 'G',
}


class TemplateDeliveryRoute(models.Model):
    _name = 'template.delivery.route'
    _description = 'Template delivery route'

    name = fields.Char(
        string="Name", 
        compute='_compute_name', 
        store=True
    )
    day = fields.Selection(
        selection=[
            ('monday', 'Monday'),
            ('tuesday', 'Tuesday'),
            ('wednesday', 'Wednesday'),
            ('thursday', 'Thursday'),
            ('friday', 'Friday'),
            ('saturday', 'Saturday'),
            ('sunday', 'Sunday')
        ],
        default='monday',
        string='Visit Day',
        required=True,
    )
    #user_assigned_ids = fields.One2many(
    #    'user.assigned.lines', 
    #    'template_delivery_route_id', 
    #    string='Users Assigned'
    #)
    #delivery_route_line_ids = fields.One2many(
    #    'delivery.route.line',
    #    'template_route_id',
    #    string='Clients to Visit'
    #)
    delivery_number_id = fields.Many2one(
        'delivery.route.number',
        string="Delivery Route Number",
    )
    #truck_id = fields.Many2one(
    #    'fleet.truck',
    #    string='Truck License Plate',
    #    related='delivery_number_id.truck_id',
    #    store=True,
    #) 
    allow_price_editing = fields.Boolean(
        string="Allow Price Editing",
        related="delivery_number_id.allow_price_editing",
        store=True,
    )
    allow_reordering = fields.Boolean(
        string="Allow Reordering",
        related="delivery_number_id.allow_reordering",
        store=True,
    )
    allow_closing_with_rake = fields.Boolean(
        string='Allow closing with rake',
        related="delivery_number_id.allow_closing_with_rake",
        store=True,
    )
    allow_cash_sale = fields.Boolean(
        string='Allow Cash Sale',
        related='delivery_number_id.allow_cash_sale',
        store=True,
        tracking=True,
        help="Reflects the cash‑sale setting of the associated delivery number."
    )
    allow_manual_address = fields.Boolean(
        string='Allow Manual Address',
        related='delivery_number_id.allow_manual_address',
        store=True,
        tracking=True,
        # help="Reflects the cash‑sale setting of the associated delivery number."
    )

    @api.depends(
        'day', 
        'delivery_number_id', 
        'delivery_number_id.number'
    )
    def _compute_name(self):
        for rec in self:
            rec.name = '{}{}'.format(rec.delivery_number_id.number, day_mapping.get(rec.day))
    #@api.depends('delivery_person_id')
    #def _compute_allowed_truck(self):
    #    for rec in self:
    #        if rec.delivery_person_id:
    #            domain = [('user_assigned_ids', 'in', rec.delivery_person_id.id)]
    #        else:
    #            domain = []
    #        rec.allowed_truck_domain = domain

    #@api.onchange('day')
    #def _onchange_day(self):
    #    for rec in self:
    #        delivery_route_lines = rec.delivery_route_line_ids.filtered(lambda x: x.client_id.visit_day != rec.day)
    #        if delivery_route_lines:
    #            delivery_route_lines.unlink()

class UserAssignedLines(models.Model):
    _name = 'user.assigned.lines'
    _description = 'User Assigned Lines'

    template_delivery_route_id = fields.Many2one(
        'template.delivery.route',
        string="Template delivery route",
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users',
        string="User"
    )
    role_id = fields.Many2one(
        'role',
        string="Role"
    )

class Role(models.Model):
    _name = 'role'
    _description = 'Role'

    name = fields.Char(string='Role Name', required=True)

