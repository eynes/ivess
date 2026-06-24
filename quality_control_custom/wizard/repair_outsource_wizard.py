# -*- coding: utf-8 -*-
from odoo import models, fields, _


class RepairOutsourceWizard(models.TransientModel):
    _name = 'repair.outsource.wizard'
    _description = 'Wizard de Tercerización'

    repair_id = fields.Many2one(
        'repair.order',
        string='Orden de reparación',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    outsource_reason_id = fields.Many2one(
        'repair.outsource.reason',
        string='Razón de tercerización',
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        self.repair_id._do_outsource(self.outsource_reason_id)
        return {'type': 'ir.actions.act_window_close'}
