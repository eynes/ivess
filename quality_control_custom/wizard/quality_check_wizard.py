
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from ..models.repair_order import FRIO_CALOR_STAGES


class QualityCheckWizard(models.TransientModel):
    _inherit = 'quality.check.wizard'


    def do_pass(self):
        self.ro_to_next_stage()
        return super().do_pass()

    def do_fail(self):
        self.ro_to_next_stage()
        return super().do_fail()
    
    def ro_to_next_stage(self):
        ro = self.current_check_id.repair_id
        stages = ro._get_stage_sequence()
        current_idx = stages.index(ro.frio_calor_stage) if ro.frio_calor_stage in stages else -1
        if current_idx == -1:
            raise UserError(_('The current stage of the repair order is not in the defined stages.'))
        ro.with_context(_frio_calor_stage_advance=True).write({'frio_calor_stage': stages[current_idx + 1]})
