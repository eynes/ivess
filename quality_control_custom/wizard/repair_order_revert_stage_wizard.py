# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..models.repair_order import FRIO_CALOR_STAGES, FRIO_CALOR_STAGE_ORDER, FRIO_CALOR_STAGE_ORDER_NO_PAINT


class RepairOrderRevertStageWizard(models.TransientModel):
    _name = 'repair.order.revert.stage.wizard'
    _description = 'Wizard para revertir etapa Frío/Calor'

    repair_id = fields.Many2one(
        comodel_name='repair.order',
        string="Orden de reparación",
        required=True,
    )

    current_stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string="Etapa actual",
        readonly=True,
    )

    target_stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string="Etapa destino",
        required=True,
    )

    @api.onchange('repair_id')
    def _onchange_repair_id(self):
        if self.repair_id:
            self.current_stage = self.repair_id.frio_calor_stage

    @api.onchange('current_stage')
    def _onchange_current_stage(self):
        """Filtra las etapas destino para mostrar solo las previas a la actual."""
        if not self.current_stage or not self.repair_id:
            return {}
        stages = self.repair_id._get_stage_sequence()
        current_idx = stages.index(self.current_stage) if self.current_stage in stages else 0
        valid_stages = stages[:current_idx]
        return {
            'domain': {
                'target_stage': [('id', 'in', valid_stages)] if not valid_stages else [],
            },
            'warning': False,
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            repair = self.env['repair.order'].browse(active_id)
            res['repair_id'] = repair.id
            res['current_stage'] = repair.frio_calor_stage
        return res

    def action_revert_stage(self):
        self.ensure_one()
        repair = self.repair_id
        stages = repair._get_stage_sequence()

        if self.target_stage not in stages:
            raise UserError(_("La etapa destino no es válida."))

        current_idx = stages.index(repair.frio_calor_stage) if repair.frio_calor_stage in stages else 0
        target_idx = stages.index(self.target_stage)

        if target_idx >= current_idx:
            raise UserError(_("La etapa destino debe ser anterior a la etapa actual."))

        old_stage_label = dict(FRIO_CALOR_STAGES).get(repair.frio_calor_stage, repair.frio_calor_stage)
        new_stage_label = dict(FRIO_CALOR_STAGES).get(self.target_stage, self.target_stage)

        repair.with_context(_revert_stage=True).frio_calor_stage = self.target_stage
        repair.message_post(
            body=_("Regresión manual de etapa: de '%s' a '%s'.", old_stage_label, new_stage_label),
        )
        return {'type': 'ir.actions.act_window_close'}
