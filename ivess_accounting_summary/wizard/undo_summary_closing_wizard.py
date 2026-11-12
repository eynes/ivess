from odoo import api, fields, models


class UndoSummaryClosingWizard(models.TransientModel):
    _name = "ivess.undo.summary.closing.wizard"
    _description = "Deshacer Cierre Mensual"

    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento Resumen",
        required=True,
        readonly=True,
    )
    closed_count = fields.Integer(string="Comprobantes", compute="_compute_counts")
    netting_count = fields.Integer(string="Neteos", compute="_compute_counts")

    @api.depends("move_id")
    def _compute_counts(self):
        for wizard in self:
            move = wizard.move_id
            wizard.closed_count = len(move._ivess_summary_closed_moves())
            wizard.netting_count = len(move._ivess_summary_netting_moves())

    def action_confirm(self):
        self.ensure_one()
        move = self.move_id.with_context(ivess_undo_confirmed=True)
        move._ivess_check_can_undo_summary()
        if move.state == "posted":
            move.button_draft()
        move.unlink()
        return {"type": "ir.actions.act_window_close"}
