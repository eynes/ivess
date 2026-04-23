# -*- coding: utf-8 -*-
from odoo import models, fields


class RepairOrderWizardStage(models.TransientModel):
    _name = 'repair.order.wizard.stage'
    _description = 'Opción de etapa para wizard de reparación'
    _order = 'sequence'

    sequence = fields.Integer()
    key = fields.Char()
    name = fields.Char()
    advance_wizard_id = fields.Many2one('repair.order.advance.stage.wizard', ondelete='cascade')
    revert_wizard_id = fields.Many2one('repair.order.revert.stage.wizard', ondelete='cascade')
