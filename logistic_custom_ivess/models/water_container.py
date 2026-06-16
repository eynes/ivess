from datetime import timedelta

from odoo import api, fields, models
from odoo.tools.translate import _

STATE_SELECTION = [
    ('prestado', 'Prestado'),
    ('en_comodato', 'En Comodato'),
    ('asignado', 'Asignado'),
]

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
        compute='_compute_assignment_date',
        store=True,
    )
    return_date = fields.Date(
        string='Return Date',
        compute='_compute_return_date',
    )
    state = fields.Selection(
        STATE_SELECTION,
        string='Status',
        required=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        'product.template',
        string="Product",
        domain=['|', ('is_returnable', '=', True), ('is_frio_calor', '=', True)],
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='N° de Serie',
    )
    is_frio_calor = fields.Boolean(
        related='product_id.is_frio_calor',
        store=True,
        string='Es Frio/Calor',
    )
    frio_calor_picking_id = fields.Many2one(
        'stock.picking',
        string='Entrega',
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
    count_outgoing_pickings = fields.Integer(
        string='Entregas',
        compute='_compute_picking_counts',
    )
    count_incoming_pickings = fields.Integer(
        string='Devoluciones',
        compute='_compute_picking_counts',
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

    @api.depends(
        'stock_move_ids',
        'stock_move_ids.state',
        'stock_move_ids.picking_id.picking_type_code',
        'stock_move_ids.picking_id.date_done',
        'is_frio_calor',
        'frio_calor_picking_id',
        'frio_calor_picking_id.date_done',
    )
    def _compute_assignment_date(self):
        for rec in self:
            if rec.is_frio_calor:
                picking = rec.frio_calor_picking_id
                rec.assignment_date = picking.date_done.date() if picking and picking.date_done else False
                continue
            outgoing_pickings = rec.stock_move_ids.filtered(
                lambda m: m.state == 'done'
                and m.picking_id.picking_type_code == 'outgoing'
            ).mapped('picking_id')
            if outgoing_pickings:
                last = outgoing_pickings.sorted('date_done', reverse=True)[:1]
                rec.assignment_date = last.date_done.date() if last.date_done else False
            else:
                rec.assignment_date = False

    @api.depends('stock_move_ids.picking_id', 'stock_move_ids.picking_id.picking_type_code')
    def _compute_picking_counts(self):
        for rec in self:
            pickings = rec.stock_move_ids.mapped('picking_id')
            rec.count_outgoing_pickings = len(
                pickings.filtered(lambda p: p.picking_type_code == 'outgoing')
            )
            rec.count_incoming_pickings = len(
                pickings.filtered(lambda p: p.picking_type_code == 'incoming')
            )

    def action_open_outgoing_pickings(self):
        move_ids = self.stock_move_ids.filtered(
            lambda m: m.picking_id.picking_type_code == 'outgoing'
        ).ids
        return {
            'name': 'Entregas',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
        }

    def action_open_incoming_pickings(self):
        move_ids = self.stock_move_ids.filtered(
            lambda m: m.picking_id.picking_type_code == 'incoming'
        ).ids
        return {
            'name': 'Devoluciones',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
        }

    @api.depends('partner_id')
    def _compute_return_date(self):
        for rec in self:
            if not rec.partner_id:
                rec.return_date = False
                continue
            route = self.env['delivery.route'].search([
                ('delivery_route_line_ids.client_id', '=', rec.partner_id.id),
                ('state', '!=', 'closed'),
            ], order='delivery_date asc', limit=1)
            rec.return_date = route.delivery_date if route else False

    @api.model
    def _cron_check_nonproductive_containers(self):
        four_weeks_ago = fields.Date.today() - timedelta(weeks=4)
        containers = self.search([
            ('is_nonproductive', '=', False),
            ('is_frio_calor', '=', False),
            ('product_id', '!=', False),
            ('partner_id', '!=', False),
        ])
        to_deactivate = self.env['water.container']
        for container in containers:
            has_recent_sale = self.env['sale.order.line'].search_count([
                ('order_id.partner_id', '=', container.partner_id.id),
                ('product_id.product_tmpl_id', '=', container.product_id.id),
                ('order_id.state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', four_weeks_ago),
            ])
            if not has_recent_sale:
                to_deactivate |= container
        if to_deactivate:
            to_deactivate.write({'is_nonproductive': True})
            for c in to_deactivate:
                c.message_post(body=_('Marcado como Improductivo: sin compras en las últimas 4 semanas.'))

    def _reactivate_for_partner_products(self, partner_id, product_tmpl_ids):
        containers = self.search([
            ('partner_id', '=', partner_id),
            ('product_id', 'in', product_tmpl_ids),
            ('is_nonproductive', '=', True),
        ])
        if containers:
            containers.write({'is_nonproductive': False})
            for c in containers:
                c.message_post(body=_('Reactivado: nueva compra del producto registrada.'))

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if not vals.get('name') or vals['name'] in ('/', 'New', 'Nuevo'):
                product_id = vals.get('product_id')
                is_fc = False
                if product_id:
                    product = self.env['product.template'].browse(product_id)
                    is_fc = product.is_frio_calor
                if is_fc:
                    vals['name'] = self.env['ir.sequence'].next_by_code('seq.frio.calor.container') or '/'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('seq.water.container') or '/'

        records = super().create(vals_list)
        return records
