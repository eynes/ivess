# -*- coding: utf-8 -*-
from odoo import models, fields, _
from ..models.repair_order import FRIO_CALOR_STAGES

_RECEIVE_STAGE_SELECTION = [(k, v) for k, v in FRIO_CALOR_STAGES if k != 'finalizado']


class RepairReceiveThirdPartyWizard(models.TransientModel):
    _name = 'repair.receive.third.party.wizard'
    _description = 'Wizard - Recibir de Tercero'

    repair_id = fields.Many2one(
        'repair.order',
        string='Orden de reparación',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    target_stage = fields.Selection(
        selection=_RECEIVE_STAGE_SELECTION,
        string='Etapa de retorno',
        required=True,
        default='hidrolavadora',
    )

    def action_confirm(self):
        self.ensure_one()
        self.repair_id._do_receive_from_third_party(self.target_stage)
        return {'type': 'ir.actions.act_window_close'}
