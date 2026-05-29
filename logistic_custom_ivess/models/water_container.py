from odoo import models, fields, api


class WaterContainer(models.Model):
    _name = 'water.container'
    _description = 'Water Container'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Container Number',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
    )
    assignment_date = fields.Date(
        string='Assignment Date',
        required=True
    )
    return_date = fields.Date(
        string='Return Date'
    )
    state_id = fields.Many2one(
        'water.container.state',
        string='Status',
        required=True,
        tracking=True
    )
    product_id = fields.Many2one(
        'product.template',
        string="Product",
        domain=[('is_returnable', '=', True)],
    )
    stock_move_ids = fields.One2many(
        'stock.move',
        'water_container_id',
        string='Stock Moves',
    )
    quantity = fields.Float(
        string='Quantity',
        compute='_compute_quantity',
        store=True,
    )
    is_nonproductive = fields.Boolean(
        string='Envase Improductivo',
        default=False,
    )

    @api.depends('stock_move_ids', 'stock_move_ids.state', 'stock_move_ids.quantity',
                 'stock_move_ids.picking_id.picking_type_code')
    def _compute_quantity(self):
        for rec in self:
            done_moves = rec.stock_move_ids.filtered(lambda m: m.state == 'done')
            qty_out = sum(
                m.quantity for m in done_moves
                if m.picking_id.picking_type_code == 'outgoing'
            )
            qty_in = sum(
                m.quantity for m in done_moves
                if m.picking_id.picking_type_code == 'incoming'
            )
            rec.quantity = qty_out - qty_in

    @api.onchange('partner_id')
    def _onchange_partner_id_fill_return_date(self):
        if self.partner_id:
            today = fields.Date.context_today(self)
            next_route = self.env['delivery.route'].search([
                ('delivery_route_line_ids.client_id', '=', self.partner_id.id),
                ('delivery_date', '>=', today),
                ('state', '!=', 'closed'),
            ], order='delivery_date asc', limit=1)
            self.return_date = next_route.delivery_date if next_route else False

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if not vals.get('name') or vals['name'] in ('/', 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.water.container') or '/'
            if not vals.get('return_date') and vals.get('partner_id'):
                today = fields.Date.context_today(self)
                next_route = self.env['delivery.route'].search([
                    ('delivery_route_line_ids.client_id', '=', vals['partner_id']),
                    ('delivery_date', '>=', today),
                    ('state', '!=', 'closed'),
                ], order='delivery_date asc', limit=1)
                if next_route:
                    vals['return_date'] = next_route.delivery_date

        records = super().create(vals_list)
        return records


class WaterContainerState(models.Model):
    _name = 'water.container.state'
    _description = 'Water Container Status'
    _order = 'code'

    name = fields.Char(string='Status', required=True)
    code = fields.Integer(
        string='Code',
        readonly=True,
        copy=False,
        index=True
    )
    is_pending_return = fields.Boolean(string="Pending return")

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        # Obtener el último código actual
        last_code = self.search([], order='code desc', limit=1).code or 0

        for vals in vals_list:
            last_code += 1
            vals['code'] = last_code

        return super(WaterContainerState, self).create(vals_list)
