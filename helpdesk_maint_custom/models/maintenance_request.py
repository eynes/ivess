# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Helpdesk Ticket',
        index=True,
    )
    request_origin = fields.Char(string='Origen')
    material_ids = fields.One2many(
        'maintenance.request.material',
        'request_id',
        string='Materials',
        copy=True,
    )

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' not in vals:
            return res
        for record in self:
            if record.stage_id.in_progress:
                record._action_reserve_materials()
            elif record.stage_id.done:
                record._action_done_materials()
        return res

    def _get_consumption_location(self):
        return (
            self.env.ref('stock.location_production', raise_if_not_found=False)
            or self.env['stock.location'].search([('usage', '=', 'production')], limit=1)
        )

    def _action_reserve_materials(self):
        dest_location = self._get_consumption_location()
        if not dest_location:
            return
        for material in self.material_ids:
            if material.stock_move_id and material.stock_move_id.state != 'cancel':
                continue
            location = material.supply_location_id
            if not material.product_id or not location:
                continue
            move = self.env['stock.move'].create({
                'product_id': material.product_id.id,
                'product_uom_qty': material.product_uom_qty,
                'product_uom': material.product_uom.id,
                'location_id': location.id,
                'location_dest_id': dest_location.id,
                'company_id': self.company_id.id,
                'origin': self.name,
            })
            material.stock_move_id = move
            move._action_confirm()
            move._action_assign()

    def _action_done_materials(self):
        dest_location = self._get_consumption_location()
        if not dest_location:
            return
        for material in self.material_ids:
            if not material.product_id:
                continue
            location = material.supply_location_id
            if not location:
                continue
            move = material.stock_move_id
            if not move or move.state == 'cancel':
                qty = material.quantity or material.product_uom_qty
                move = self.env['stock.move'].create({
                    'product_id': material.product_id.id,
                    'product_uom_qty': qty,
                    'product_uom': material.product_uom.id,
                    'location_id': location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                })
                material.stock_move_id = move
                move._action_confirm()
                move._action_assign()
            if move.state == 'done':
                continue
            if not move.move_line_ids:
                qty = material.quantity or material.product_uom_qty
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': qty,
                    'lot_id': material.lot_id.id,
                    'picked': True,
                    'company_id': move.company_id.id,
                })
            else:
                for ml in move.move_line_ids:
                    ml.picked = True
            move._action_done()
