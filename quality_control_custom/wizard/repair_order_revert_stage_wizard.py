# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..models.repair_order import FRIO_CALOR_STAGES


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

    valid_stage_ids = fields.One2many(
        comodel_name='repair.order.wizard.stage',
        inverse_name='revert_wizard_id',
        string="Etapas disponibles",
    )

    target_stage_id = fields.Many2one(
        comodel_name='repair.order.wizard.stage',
        string="Etapa destino",
        domain="[('revert_wizard_id', '=', id)]",
    )

    def action_revert_stage(self):
        self.ensure_one()
        repair = self.repair_id
        stages = repair._get_stage_sequence()
        target_key = self.target_stage_id.key

        if target_key not in stages:
            raise UserError(_("La etapa destino no es válida."))

        current_idx = stages.index(repair.frio_calor_stage) if repair.frio_calor_stage in stages else 0
        target_idx = stages.index(target_key)

        if target_idx >= current_idx:
            raise UserError(_("La etapa destino debe ser anterior a la etapa actual."))

        old_stage_label = dict(FRIO_CALOR_STAGES).get(repair.frio_calor_stage, repair.frio_calor_stage)
        new_stage_label = dict(FRIO_CALOR_STAGES).get(target_key, target_key)

        repair.with_context(_revert_stage=True).frio_calor_stage = target_key
        repair.message_post(
            body=_("Regresión manual de etapa: de '%s' a '%s'.", old_stage_label, new_stage_label),
        )
        return {'type': 'ir.actions.act_window_close'}
