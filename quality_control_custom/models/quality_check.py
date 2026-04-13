# -*- coding: utf-8 -*-
from odoo import models, _


class QualityCheck(models.Model):
    _inherit = 'quality.check'

    def do_fail(self):
        res = super().do_fail()
        for check in self:
            picking_type = (
                check.picking_id.picking_type_id
                or check.point_id.picking_type_ids[:1]
            )
            if picking_type.is_frio_calor:
                check._create_auto_repair_order()
        return res

    def _create_auto_repair_order(self):
        self.ensure_one()
        product = self.product_id
        lot = self.lot_ids[:1] if self.lot_ids else self.env['stock.lot']
        repair_vals = {
            'product_id': product.id,
            'lot_id': lot.id if lot else False,
            'quality_check_id': self.id,
        }
        repair = self.env['repair.order'].create(repair_vals)
        self.repair_id = repair.id
        self.message_post(
            body=_("Se creó automáticamente la orden de reparación %s por fallo en control de calidad.", repair.name),
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
            'res_id': self.repair_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
