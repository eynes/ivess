from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    free_of_charge = fields.Boolean(
        default=False,
        string='Sin Cargo',
    )

    fecha_programada = fields.Datetime(
        string='Fecha Programada',
        help='Fecha programada de la orden de reparación asociada a este renglón de servicio.',
    )
    turno = fields.Selection(
        [
            ('manana', 'Turno Mañana'),
            ('tarde', 'Turno Tarde'),
        ],
        string='Turno',
    )

    def _get_synced_repair_order(self):
        self.ensure_one()
        return self.order_id.sudo().repair_order_ids.filtered(
            lambda ro: ro.sale_order_line_id.id == self.id and ro.state != 'cancel'
        )

    def _create_repair_order(self):
        res = super()._create_repair_order()
        for line in self:
            if not (line.fecha_programada or line.turno):
                continue
            repair = line._get_synced_repair_order()
            if not repair:
                continue
            vals = {}
            if line.fecha_programada:
                vals['schedule_date'] = line.fecha_programada
            if line.turno:
                vals['turno'] = line.turno
            repair.with_context(_sync_from_sale_line=True).write(vals)
        return res

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('_sync_from_repair'):
            sync_vals = {}
            if 'fecha_programada' in vals:
                sync_vals['schedule_date'] = vals['fecha_programada']
            if 'turno' in vals:
                sync_vals['turno'] = vals['turno']
            if sync_vals:
                for line in self:
                    repair = line._get_synced_repair_order()
                    if repair:
                        repair.with_context(_sync_from_sale_line=True).write(sync_vals)
        return res

    @api.constrains('free_of_charge', 'product_id')
    def _check_free_of_charge(self):
        for line in self:
            if line.free_of_charge and not line.product_id.product_tmpl_id.allow_free_of_charge:
                raise ValidationError(_(
                    'El producto "%s" no permite ser marcado como Sin Cargo.'
                ) % line.product_id.display_name)

    @api.onchange('product_id')
    def _onchange_product_id_free_of_charge(self):
        if self.free_of_charge and not self.product_id.product_tmpl_id.allow_free_of_charge:
            self.free_of_charge = False
