# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class QualityCheck(models.Model):
    _inherit = 'quality.check'

    auto_repair_order_id = fields.Many2one(
        comodel_name='repair.order',
        string="Orden de Reparación Automática",
        copy=False,
        readonly=True,
    )

    def do_fail(self):
        res = super().do_fail()
        for check in self:
            if check.auto_repair_order_id:
                continue
            picking_type = (
                check.picking_id.picking_type_id
                or check.point_id.picking_type_ids[:1]
            )
            if picking_type.is_frio_calor:
                check._create_auto_repair_order(picking_type)
        return res

    def do_pass(self):
        res = super().do_pass()
        for check in self:
            if check.auto_repair_order_id:
                continue
            picking_type = (
                check.picking_id.picking_type_id
                or check.point_id.picking_type_ids[:1]
            )
            if picking_type.is_frio_calor:
                check._create_auto_repair_order(picking_type)
        return res

    def _create_auto_repair_order(self, picking_type=None):
        self.ensure_one()
        product = self.product_id
        lot = self.lot_ids[:1] if self.lot_ids else self.env['stock.lot']

        if not picking_type:
            raise UserError(_(
                "No se puede crear la orden de reparación automática para el control de calidad '%s' "
                "porque el punto de control no tiene configurado un tipo de operación Frío/Calor. "
                "Asigne un tipo de operación adecuado en el punto de control de calidad.",
                self.point_id.name or self.name,
            ))

        if picking_type:
            missing = []
            if not picking_type.default_product_location_src_id:
                missing.append(_("• Ubicación de origen del producto"))
            if not picking_type.default_product_location_dest_id:
                missing.append(_("• Ubicación de destino del producto"))
            if not picking_type.default_remove_location_dest_id:
                missing.append(_("• Ubicación de destino de las partes eliminadas"))
            if missing:
                raise UserError(_(
                    "No se puede crear la orden de reparación automática porque el tipo de operación "
                    "'%(name)s' no tiene configuradas las siguientes ubicaciones por defecto:\n\n%(fields)s\n\n"
                    "Configúrelas en la pestaña de ubicaciones del tipo de operación.",
                    name=picking_type.name,
                    fields="\n".join(missing),
                ))

        # Dejamos que repair.order calcule sus propios defaults de ubicación
        # desde picking_type_id. Solo aplicamos fallbacks para los campos que
        # queden vacíos cuando el tipo de operación no es de reparación.
        location_fields = ['product_location_src_id', 'product_location_dest_id', 'parts_location_id']
        ctx = {'default_picking_type_id': picking_type.id} if picking_type else {}
        computed = self.env['repair.order'].with_context(**ctx).default_get(location_fields)

        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        fallback = (self.picking_id and self.picking_id.location_dest_id) or warehouse.lot_stock_id
        production_loc = self.env.ref('stock.location_production', raise_if_not_found=False)

        repair_vals = {
            'product_id': product.id,
            'lot_id': lot.id if lot else False,
            'quality_check_id': self.id,
            'product_location_src_id': computed.get('product_location_src_id') or fallback.id,
            'product_location_dest_id': computed.get('product_location_dest_id') or fallback.id,
            'parts_location_id': computed.get('parts_location_id') or (production_loc and production_loc.id) or fallback.id,
        }
        if picking_type:
            repair_vals['picking_type_id'] = picking_type.id

        repair = self.env['repair.order'].create(repair_vals)
        repair.action_repair_start()
        self.auto_repair_order_id = repair.id
        result_label = _("aprobación") if self.quality_state == 'pass' else _("fallo")
        self.message_post(
            body=_("Se creó automáticamente la orden de reparación %s por %s en control de calidad.", repair.name, result_label),
        )
        repair.message_post(
            body=_("Orden creada automáticamente desde el control de calidad %s (Origen: %s).",
                   self.name, self.picking_id.name or self.name),
        )

    def action_view_auto_repair(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order',
            'res_id': self.auto_repair_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
