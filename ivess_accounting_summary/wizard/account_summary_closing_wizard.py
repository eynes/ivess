from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountSummaryClosingWizard(models.TransientModel):
    _name = "ivess.accounting.summary.wizard"
    _inherit = ["ivess.accounting.summary.engine"]
    _description = "Asistente de Cierre Mensual (Contabilidad Resumida)"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string="Desde", required=True)
    date_to = fields.Date(string="Hasta", required=True)
    operational_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Diarios Operativos a Resumir",
        required=True,
        domain="[('company_id', '=', company_id), ('x_is_operational_journal', '=', True), ('x_is_legal_journal', '=', False)]",
        help=(
            "Diarios de Ventas/Compras/Pagos cuyo detalle transaccional "
            "del período se va a netear y resumir."
        ),
    )
    legal_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de Refundición (Legal)",
        required=True,
        domain="[('company_id', '=', company_id), ('x_is_legal_journal', '=', True)]",
    )
    summary_move_date = fields.Date(
        string="Fecha del Asiento Resumen",
        help=(
            "Fecha contable del asiento resumen en el Diario Legal. Si se "
            "deja vacío, se usa la fecha Hasta del período."
        ),
    )
    summary_move_ref = fields.Char(
        string="Referencia del Asiento Resumen",
        help=(
            "Referencia/glosa del asiento resumen en el Diario Legal. Si se "
            "deja vacía, se genera automáticamente a partir del período."
        ),
    )
    run_in_background = fields.Boolean(
        string="Procesar en segundo plano",
        help=(
            "Deja el cierre corriendo por tandas y abre su pantalla de avance, "
            "sin esperar acá a que termine. Los cierres grandes siempre se "
            "procesan así."
        ),
    )
    netting_move_ids = fields.Many2many(
        comodel_name="account.move",
        relation="ivess_summary_wizard_netting_move_rel",
        column1="wizard_id",
        column2="move_id",
        string="Asientos de Neteo (Operativos)",
        readonly=True,
    )
    summary_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento Resumen (Legal)",
        readonly=True,
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.operational_journal_ids = False
        self.legal_journal_id = False

    def action_generate_summary(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("El período (Desde/Hasta) es inválido."))

        self.env["ivess.accounting.summary.job"]._summary_check_no_active_job(
            self.company_id, self.operational_journal_ids, self.date_from, self.date_to
        )
        candidate_lines = self._summary_candidate_lines()
        if not candidate_lines:
            raise UserError(_("No hay apuntes sin resumir en ese período/diarios."))

        # Un cierre grande no entra en un pedido web (tarda en proporción a los
        # apuntes y el servidor corta los pedidos largos): se encola y lo
        # procesa un cron por tandas. Los chicos se resuelven en el momento.
        sync_limit = self._summary_param("sync_line_limit", 1000)
        if (
            self.run_in_background or len(candidate_lines) > sync_limit
        ) and not self.env.context.get("summary_force_sync"):
            return self._summary_enqueue_job(candidate_lines)

        contrib = self._summary_close_lines(candidate_lines)
        legal_line_vals = self._summary_legal_line_vals(
            contrib["pl"], contrib["bridge"], contrib["debt"]
        )
        if not legal_line_vals:
            raise UserError(_("No hay montos para resumir en el período seleccionado."))

        Move = self.env["account.move"].with_context(ivess_summary_close=True)
        summary_move = Move.create(self._summary_move_vals(legal_line_vals))
        summary_move.action_post()

        self._summary_mark(
            self.env["account.move"].browse(contrib["closed_move_ids"]),
            "x_closed_by_summary_move_id",
            summary_move,
        )
        self._summary_log_closed(summary_move, len(contrib["closed_move_ids"]))

        self.write(
            {
                "summary_move_id": summary_move.id,
                "netting_move_ids": [(6, 0, contrib["netting_moves"].ids)],
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _summary_enqueue_job(self, candidate_lines):
        """Deja el cierre en segundo plano y abre el trabajo para seguirlo."""
        self._summary_check_unmapped_debt_accounts(
            candidate_lines.filtered(
                lambda line: not line.account_id.x_legal_debt_account_id
            )
        )
        job = self.env["ivess.accounting.summary.job"].create(
            {
                "company_id": self.company_id.id,
                "date_from": self.date_from,
                "date_to": self.date_to,
                "operational_journal_ids": [(6, 0, self.operational_journal_ids.ids)],
                "legal_journal_id": self.legal_journal_id.id,
                "summary_move_date": self.summary_move_date,
                "summary_move_ref": self.summary_move_ref,
                "snapshot_line_id": max(candidate_lines.ids),
                "total_lines": len(candidate_lines),
            }
        )
        job._schedule()
        return {
            "type": "ir.actions.act_window",
            "res_model": job._name,
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_summary_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.summary_move_id.id,
            "view_mode": "form",
            "target": "current",
        }
