# -*- coding: utf-8 -*-
import logging
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_frio_calor = fields.Boolean(
        string="Es operación FC",
        default=False,
    )


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    origin_picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Picking de origen",
        copy=False,
        readonly=True,
        index=True,
    )


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('_frio_calor_no_auto_lot'):
            for vals in vals_list:
                if vals.get('lot_id') and vals.get('product_id'):
                    product = self.env['product.product'].browse(vals['product_id'])
                    if product.product_tmpl_id.repair_equipment_type == 'frio_calor':
                        vals.pop('lot_id')
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('_frio_calor_no_auto_lot') and 'lot_id' in vals:
            frio = self.filtered(
                lambda ml: ml.product_id.product_tmpl_id.repair_equipment_type == 'frio_calor')
            others = self - frio
            vals_no_lot = {k: v for k, v in vals.items() if k != 'lot_id'}
            if others:
                super(StockMoveLine, others).write(vals)
            if frio and vals_no_lot:
                super(StockMoveLine, frio).write(vals_no_lot)
            elif frio:
                pass
            return True
        return super().write(vals)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        if 'product_uom_qty' in vals:
            frio = self.filtered(lambda m: m.picking_id.picking_type_id.is_frio_calor)
            others = self - frio
            if others:
                super(StockMove, others).write(vals)
            if frio:
                super(StockMove, frio).with_context(_frio_calor_no_auto_lot=True).write(vals)
            return True
        return super().write(vals)

    def _action_assign(self, force_qty=False):
        frio = self.filtered(lambda m: m.picking_id.picking_type_id.is_frio_calor)
        others = self - frio
        res = False
        if others:
            res = super(StockMove, others)._action_assign(force_qty=force_qty)
        if frio:
            res = super(StockMove, frio).with_context(
                _frio_calor_no_auto_lot=True)._action_assign(force_qty=force_qty)
        return res


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_frio_calor = fields.Boolean(
        string="Es operación FC",
        related='picking_type_id.is_frio_calor',
        readonly=True,
        store=True,
    )

    outsource_reason_id = fields.Many2one(
        comodel_name='repair.outsource.reason',
        string="Razón de tercerización",
        readonly=True,
        copy=False,
    )

    repair_order_ids = fields.One2many(
        comodel_name='repair.order',
        inverse_name='origin_picking_id',
        string="Órdenes de reparación",
        readonly=True,
    )
    repair_order_count = fields.Integer(
        compute='_compute_repair_order_count',
        string="Órdenes de reparación",
    )

    def _compute_repair_order_count(self):
        for picking in self:
            picking.repair_order_count = len(picking.repair_order_ids)

    def action_view_repair_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order',
            'view_mode': 'list,form',
            'domain': [('origin_picking_id', '=', self.id)],
            'context': {'default_origin_picking_id': self.id},
        }

    def _action_assign(self, force_qty=False):
        frio = self.filtered('is_frio_calor')
        others = self - frio
        res = False
        if others:
            res = super(StockPicking, others)._action_assign(force_qty=force_qty)
        if frio:
            res = super(StockPicking, frio).with_context(
                _frio_calor_no_auto_lot=True)._action_assign(force_qty=force_qty)
        return res

    def _action_done(self):
        self.lot_validations()
        res = super()._action_done()
        for picking in self:
            if picking.picking_type_id.is_frio_calor:
                picking._create_frio_calor_repair_orders()
        return res

    def _create_frio_calor_repair_orders(self):
        self.ensure_one()
        RepairOrder = self.env['repair.order']

        # Resolver el tipo de operación de reparación desde el almacén del picking de ingreso.
        # repair.order requiere code='repair_operation' para computar sus ubicaciones.
        warehouse = self.picking_type_id.warehouse_id
        repair_type = warehouse.repair_type_id or self.env['stock.picking.type'].search([
            ('code', '=', 'repair_operation'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        
        if not repair_type:
            raise ValidationError(_(
                "No se encontró un tipo de operación de reparación para el almacén %s. "
                "Configure el tipo de reparación del almacén.",
                warehouse.display_name or self.company_id.name,
            ))

        # Validar que el tipo de reparación tenga las ubicaciones por defecto configuradas.
        missing = []
        if not repair_type.default_product_location_src_id:
            missing.append(_("• Ubicación de origen del producto"))
        if not repair_type.default_product_location_dest_id:
            missing.append(_("• Ubicación de destino del producto"))
        if not repair_type.default_remove_location_dest_id:
            missing.append(_("• Ubicación de destino de las partes eliminadas"))
        if missing:
            raise ValidationError(_(
                "No se puede crear la orden de reparación automática porque el tipo de operación "
                "'%(name)s' no tiene configuradas las siguientes ubicaciones por defecto:\n\n%(fields)s\n\n"
                "Configúrelas en la pestaña de ubicaciones del tipo de operación.",
                name=repair_type.name,
                fields="\n".join(missing),
            ))

        created_lots = set()
        for line in self.move_line_ids:
            product = line.product_id
            lot = line.lot_id
            if not lot or lot.id in created_lots:
                continue
            if product.product_tmpl_id.repair_equipment_type != 'frio_calor':
                continue
            if RepairOrder.search_count([
                ('lot_id', '=', lot.id),
                ('state', 'not in', ['cancel', 'done']),
            ]):
                raise ValidationError(
                    _("Ya existe una orden de reparación abierta para el N° de serie %s.") % lot.name)
            try:
                with self.env.cr.savepoint():
                    # Solo se pasa picking_type_id; los computes nativos de repair.order
                    # resuelven product_location_src_id, product_location_dest_id y
                    # parts_location_id (related readonly) desde repair_type.
                    repair = RepairOrder.create({
                        'product_id': product.id,
                        'lot_id': lot.id,
                        'product_qty': line.quantity or 1.0,
                        'partner_id': self.partner_id.id or False,
                        'company_id': self.company_id.id,
                        'picking_type_id': repair_type.id,
                        'origin_picking_id': self.id,
                    })
                created_lots.add(lot.id)
                repair.message_post(body=_(
                    "Orden creada automáticamente al validar el picking %s.", self.name))
                self.message_post(body=_(
                    "Se creó la orden de reparación %s para el N° de serie %s.",
                    repair.name, lot.name))
            except Exception as e:
                _logger.exception(
                    "Auto repair order failed picking=%s lot=%s: %s", self.name, lot.name, e)
                self.message_post(body=_(
                    "No se pudo crear la orden de reparación para el N° de serie %s. "
                    "Revise la configuración del tipo de operación de reparación.", lot.name))
        return True

    def lot_validations(self):
        for picking in self:
            if picking.is_frio_calor and picking.state in ['assigned']:
                for line in picking.move_ids:
                    product = line.product_id
                    lot = line.lot_ids
                    if product.product_tmpl_id.repair_equipment_type == 'frio_calor' and not lot:
                        raise ValidationError(_("El producto FC %s requiere un N° de serie.") % product.display_name)
        return True