from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .water_container import STATE_SELECTION


class WaterContainerTransfer(models.Model):
    _name = 'water.container.transfer'
    _description = 'Traslado de envases entre cuentas'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    origin_partner_id = fields.Many2one(
        'res.partner',
        string='Cuenta Origen',
        required=True,
        tracking=True,
    )
    dest_partner_id = fields.Many2one(
        'res.partner',
        string='Cuenta Destino',
        required=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain=['|', ('is_returnable', '=', True), ('is_frio_calor', '=', True)],
    )
    is_frio_calor = fields.Boolean(
        related='product_id.is_frio_calor',
    )
    quantity = fields.Float(
        string='Cantidad',
        default=1.0,
    )
    lot_ids = fields.Many2many(
        'stock.lot',
        string='N° de Serie',
        domain="[('product_id', '=', product_id)]",
    )
    container_state = fields.Selection(
        STATE_SELECTION,
        string='Estado del Envase',
        default='prestado',
    )
    date = fields.Datetime(
        string='Fecha',
        required=True,
        default=fields.Datetime.now,
    )
    note = fields.Text(
        string='Observaciones',
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    return_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operación de Devolución',
        required=True,
        domain="[('code', '=', 'incoming'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_picking_types()[0],
    )
    delivery_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operación de Entrega',
        required=True,
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_picking_types()[1],
    )
    return_picking_id = fields.Many2one(
        'stock.picking',
        string='Devolución',
        readonly=True,
        copy=False,
    )
    delivery_picking_id = fields.Many2one(
        'stock.picking',
        string='Entrega',
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [('draft', 'Borrador'), ('done', 'Hecho')],
        string='Estado',
        default='draft',
        readonly=True,
        tracking=True,
    )

    def _default_picking_types(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        delivery = warehouse.out_type_id
        return (delivery.return_picking_type_id or warehouse.in_type_id), delivery

    @api.depends('origin_partner_id', 'dest_partner_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = _('Traslado de envases: %(origen)s → %(destino)s') % {
                'origen': rec.origin_partner_id.display_name or '?',
                'destino': rec.dest_partner_id.display_name or '?',
            }

    def action_confirm(self):
        for rec in self:
            rec._check_transfer()
            rec.return_picking_id = rec._create_done_picking(
                rec.return_picking_type_id,
                rec.origin_partner_id,
                rec.origin_partner_id.property_stock_customer,
                rec.return_picking_type_id.default_location_dest_id,
            )
            rec.delivery_picking_id = rec._create_done_picking(
                rec.delivery_picking_type_id,
                rec.dest_partner_id,
                rec.delivery_picking_type_id.default_location_src_id,
                rec.dest_partner_id.property_stock_customer,
            )
            rec.state = 'done'
            for partner in rec.origin_partner_id | rec.dest_partner_id:
                partner.message_post(body=_('%(traslado)s: %(cantidad)s x %(producto)s.') % {
                    'traslado': rec.display_name,
                    'cantidad': rec._transfer_quantity(),
                    'producto': rec.product_id.display_name,
                })

    def _transfer_quantity(self):
        return len(self.lot_ids) if self.is_frio_calor else self.quantity

    def _check_transfer(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('El traslado ya está hecho.'))
        if self.origin_partner_id == self.dest_partner_id:
            raise UserError(_('La cuenta origen y la destino son la misma.'))
        for partner in self.origin_partner_id | self.dest_partner_id:
            if partner.company_id and partner.company_id != self.company_id:
                raise UserError(_('%(cuenta)s es de %(cia)s y el traslado es de %(cia_traslado)s.') % {
                    'cuenta': partner.display_name,
                    'cia': partner.company_id.name,
                    'cia_traslado': self.company_id.name,
                })
        containers = self.env['water.container'].search([
            ('partner_id', '=', self.origin_partner_id.id),
            ('product_id', '=', self.product_id.product_tmpl_id.id),
        ])
        if self.is_frio_calor:
            if not self.lot_ids:
                raise UserError(_('Elegí los números de serie de los equipos que se trasladan.'))
            missing = self.lot_ids - containers.filtered('is_frio_calor').lot_id
            if missing:
                raise UserError(_('%(cuenta)s no tiene asignados los equipos %(series)s.') % {
                    'cuenta': self.origin_partner_id.display_name,
                    'series': ', '.join(missing.mapped('name')),
                })
        else:
            if self.quantity <= 0:
                raise UserError(_('La cantidad tiene que ser mayor que cero.'))
            available = sum(containers.filtered(
                lambda c: not c.is_frio_calor and c.state == self.container_state
            ).mapped('quantity'))
            if self.quantity > available:
                raise UserError(_('%(cuenta)s tiene %(disponibles)s envases de %(producto)s en estado %(estado)s.') % {
                    'cuenta': self.origin_partner_id.display_name,
                    'disponibles': available,
                    'producto': self.product_id.display_name,
                    'estado': dict(STATE_SELECTION)[self.container_state],
                })

    def _create_done_picking(self, picking_type, partner, location, location_dest):
        """Movimiento validado que pasa por la sincronización de envases de
        stock.picking._action_done()."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': partner.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'origin': self.display_name,
            'company_id': self.company_id.id,
            'scheduled_date': self.date,
            'move_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'product_uom_qty': self._transfer_quantity(),
                'product_uom': self.product_id.uom_id.id,
                'location_id': location.id,
                'location_dest_id': location_dest.id,
                'container_state': False if self.is_frio_calor else self.container_state,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        if self.is_frio_calor:
            move.move_line_ids.unlink()
            move.move_line_ids = [(0, 0, {
                'product_id': self.product_id.id,
                'lot_id': lot.id,
                'quantity': 1.0,
                'location_id': location.id,
                'location_dest_id': location_dest.id,
                'picking_id': picking.id,
            }) for lot in self.lot_ids]
        else:
            move.quantity = self.quantity
        move.picked = True
        picking._action_done()
        if picking.state != 'done':
            raise UserError(_('No se pudo validar %s.') % picking.display_name)
        return picking
