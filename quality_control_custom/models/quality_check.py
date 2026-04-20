# -*- coding: utf-8 -*-
from odoo import models, fields, _


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
        repair_vals = {
            'product_id': product.id,
            'lot_id': lot.id if lot else False,
            'quality_check_id': self.id,
            'picking_type_id': picking_type.id if picking_type else False,
        }
        repair = self.env['repair.order'].create(repair_vals)
        repair.action_repair_start()
        self.auto_repair_order_id = repair.id
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
            'res_id': self.auto_repair_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
