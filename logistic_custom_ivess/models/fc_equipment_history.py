from odoo import api, fields, models, _


class FcEquipmentHistory(models.Model):
    _name = 'fc.equipment.history'
    _description = 'Historial de equipos F/C por cliente'
    _order = 'delivery_date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        index=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='N° de Serie',
        required=True,
        index=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Modelo',
        related='lot_id.product_id',
        store=True,
        readonly=True,
    )
    delivery_date = fields.Date(
        string='Fecha de Entrega',
        index=True,
        readonly=True,
    )
    delivery_picking_id = fields.Many2one(
        'stock.picking',
        string='Remito de Entrega',
        index='btree_not_null',
        readonly=True,
    )
    return_date = fields.Date(
        string='Fecha de Retiro',
        readonly=True,
    )
    return_picking_id = fields.Many2one(
        'stock.picking',
        string='Remito de Retiro',
        index='btree_not_null',
        readonly=True,
    )
    state = fields.Selection(
        [('en_cliente', 'En el cliente'), ('retirado', 'Retirado')],
        string='Estado',
        compute='_compute_state',
        store=True,
        index=True,
    )
    reason = fields.Selection(
        [
            ('entrega', 'Entrega'),
            ('cambio', 'Cambio'),
            ('traslado', 'Traslado entre cuentas'),
            ('retiro', 'Retiro'),
        ],
        string='Motivo',
        default='entrega',
        readonly=True,
    )
    contract_number = fields.Char(string='N° de Contrato')
    work_order = fields.Char(string='Orden de Trabajo')
    repair_order_id = fields.Many2one(
        'repair.order',
        string='Orden de Reparación',
    )
    source = fields.Selection(
        [('odoo', 'Odoo'), ('migrado', 'Migrado de Aguas')],
        string='Origen',
        default='odoo',
        required=True,
        readonly=True,
    )
    notes = fields.Text(string='Observaciones')

    _delivery_picking_lot_uniq = models.Constraint(
        'UNIQUE(delivery_picking_id, lot_id)',
        'El equipo ya tiene una línea para ese remito de entrega.',
    )

    @api.depends('return_date', 'return_picking_id')
    def _compute_state(self):
        for rec in self:
            rec.state = 'retirado' if rec.return_date or rec.return_picking_id else 'en_cliente'

    # ------------------------------------------------------------------
    # Alta y cierre de líneas a partir de los remitos validados
    # ------------------------------------------------------------------
    @api.model
    def _picking_date(self, picking):
        return fields.Date.context_today(self, picking.date_done or fields.Datetime.now())

    @api.model
    def _fc_lines_by_direction(self, picking):
        """Series de frío/calor del remito, separadas en entregas (de una
        ubicación interna a la de clientes) y retiros (de la de clientes a una
        interna). Los movimientos internos (taller, Loop, entre depósitos) no
        cuentan."""
        deliveries = self.env['stock.lot']
        returns = self.env['stock.lot']
        for line in picking.move_line_ids:
            if not line.lot_id or not line.product_id.product_tmpl_id.is_frio_calor:
                continue
            src, dest = line.location_id.usage, line.location_dest_id.usage
            if dest == 'customer' and src != 'customer':
                deliveries |= line.lot_id
            elif src == 'customer' and dest != 'customer':
                returns |= line.lot_id
        return deliveries, returns

    @api.model
    def _sync_from_picking(self, picking):
        """Registra en el historial lo que hizo un remito validado. Se puede
        llamar de nuevo con el mismo remito sin duplicar líneas."""
        if not picking.partner_id:
            return
        deliveries, returns = self._fc_lines_by_direction(picking)
        for lot in returns:
            self._register_return(lot, picking)
        for lot in deliveries:
            self._register_delivery(lot, picking)

    @api.model
    def _register_delivery(self, lot, picking):
        partner = picking.partner_id
        existing = self.search([('delivery_picking_id', '=', picking.id), ('lot_id', '=', lot.id)], limit=1)
        if existing:
            return existing
        date = self._picking_date(picking)
        transfer = self.env['water.container.transfer'].search(
            [('delivery_picking_id', '=', picking.id)], limit=1,
        )
        if transfer:
            reason = 'traslado'
        elif self.search_count([
            ('partner_id', '=', partner.id),
            ('company_id', '=', picking.company_id.id),
            ('return_date', '=', date),
            ('lot_id', '!=', lot.id),
        ]):
            reason = 'cambio'
        else:
            reason = 'entrega'
        return self.create({
            'partner_id': partner.id,
            'company_id': picking.company_id.id,
            'lot_id': lot.id,
            'delivery_date': date,
            'delivery_picking_id': picking.id,
            'reason': reason,
            'source': 'odoo',
        })

    @api.model
    def _register_return(self, lot, picking):
        partner = picking.partner_id
        if self.search_count([('return_picking_id', '=', picking.id), ('lot_id', '=', lot.id)]):
            return
        line = self.search([
            ('lot_id', '=', lot.id),
            ('partner_id', '=', partner.id),
            ('company_id', '=', picking.company_id.id),
            ('return_date', '=', False),
            ('return_picking_id', '=', False),
        ], order='delivery_date desc, id desc', limit=1)
        if not line:
            return
        date = self._picking_date(picking)
        line.write({'return_date': date, 'return_picking_id': picking.id})
        # Cambio: ese mismo día se entregó otra serie al mismo cliente.
        self.search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', picking.company_id.id),
            ('delivery_date', '=', date),
            ('reason', '=', 'entrega'),
            ('lot_id', '!=', lot.id),
        ]).write({'reason': 'cambio'})

    @api.model
    def _load_initial_history(self):
        """Arma el historial con los remitos ya hechos. Se puede correr desde el
        shell (`env['fc.equipment.history']._load_initial_history()`) las veces
        que haga falta: no duplica líneas."""
        lines = self.env['stock.move.line'].search([
            ('state', '=', 'done'),
            ('lot_id', '!=', False),
            ('product_id.product_tmpl_id.is_frio_calor', '=', True),
            '|',
            ('location_id.usage', '=', 'customer'),
            ('location_dest_id.usage', '=', 'customer'),
        ])
        pickings = lines.picking_id.sorted(lambda p: (p.date_done or fields.Datetime.now(), p.id))
        for picking in pickings:
            self._sync_from_picking(picking)
        return len(pickings)
