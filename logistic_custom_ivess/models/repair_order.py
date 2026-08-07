from odoo import models, fields


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    turno = fields.Selection(
        [
            ('manana', 'Turno Mañana'),
            ('tarde', 'Turno Tarde'),
        ],
        string='Turno',
    )

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('_sync_from_sale_line'):
            sync_vals = {}
            if 'schedule_date' in vals:
                sync_vals['fecha_programada'] = vals['schedule_date']
            if 'turno' in vals:
                sync_vals['turno'] = vals['turno']
            if sync_vals:
                for repair in self:
                    if repair.sale_order_line_id:
                        repair.sale_order_line_id.with_context(_sync_from_repair=True).write(sync_vals)
        return res
