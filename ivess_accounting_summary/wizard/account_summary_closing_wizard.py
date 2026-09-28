from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountSummaryClosingWizard(models.TransientModel):
    _name = "ivess.accounting.summary.wizard"
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

        candidate_lines = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("journal_id", "in", self.operational_journal_ids.ids),
                ("move_id.state", "=", "posted"),
                ("move_id.x_is_summary_entry", "=", False),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("x_summary_move_id", "=", False),
            ]
        )
        if not candidate_lines:
            raise UserError(_("No hay apuntes sin resumir en ese período/diarios."))

        # Las líneas sobre una cuenta de deudores/acreedores mapeada a una
        # cuenta legal son la "deuda" a trasladar; el resto son resultados
        # e impuestos a netear a cero en el diario operativo.
        debt_lines = candidate_lines.filtered(
            lambda line: line.account_id.x_legal_debt_account_id
        )
        pl_lines = candidate_lines - debt_lines

        # Una cuenta de deudores/acreedores reconciliable sin Cuenta de Deuda
        # Legal configurada caería en pl_lines y se netearía como una cuenta
        # de resultado más: todos los partners mezclados en un único monto,
        # sin desglose por comprobante/contacto. Se bloquea en vez de generar
        # un asiento legal con la deuda perdida.
        unmapped_debt_accounts = pl_lines.account_id.filtered(
            lambda account: account.account_type
            in ("asset_receivable", "liability_payable")
            and not account.x_legal_debt_account_id
        )
        if unmapped_debt_accounts:
            raise UserError(
                _(
                    "Las siguientes cuentas de deudores/acreedores no tienen "
                    "configurada una Cuenta de Deuda Legal: %s. Configurala "
                    "antes de cerrar el período o se perdería el desglose "
                    "por comprobante/contacto."
                )
                % ", ".join(unmapped_debt_accounts.mapped("display_name"))
            )

        currency = self.company_id.currency_id
        # Se cachea el residual ANTES de reconciliar nada: una vez conciliada
        # contra el neteo, amount_residual pasa a 0 y perderíamos el monto
        # real (deuda legal y/o cuenta puente) a trasladar.
        debt_residuals = {line.id: line.amount_residual for line in debt_lines}
        open_debt_lines = debt_lines.filtered(
            lambda line: not currency.is_zero(debt_residuals[line.id])
        )

        # La porción de cada comprobante ya cobrada/pagada antes del cierre
        # no genera deuda legal, pero su venta e impuestos igual deben
        # reconocerse: se imputa agregada (sin desglose por partner) a una
        # cuenta puente, en vez de a la cuenta de deuda legal.
        collected_by_line = {}
        for line in debt_lines:
            collected = line.balance - debt_residuals[line.id]
            if currency.is_zero(collected):
                continue
            if not line.account_id.x_legal_bridge_account_id:
                raise UserError(
                    _(
                        "%s tiene comprobantes ya cobrados en el período "
                        "pero no tiene configurada una Cuenta Puente "
                        "(Cobrado en el Período)."
                    )
                    % line.account_id.display_name
                )
            collected_by_line[line.id] = collected

        netting_moves = self.env["account.move"]
        period_label = _(
            "%(date_from)s a %(date_to)s",
            date_from=self.date_from,
            date_to=self.date_to,
        )

        for journal in self.operational_journal_ids:
            journal_pl_lines = pl_lines.filtered(
                lambda line, journal=journal: line.journal_id == journal
            )
            journal_debt_lines = debt_lines.filtered(
                lambda line, journal=journal: line.journal_id == journal
            )
            journal_open_debt_lines = journal_debt_lines.filtered(
                lambda line: not currency.is_zero(debt_residuals[line.id])
            )
            if not journal_pl_lines and not journal_debt_lines:
                continue

            pl_totals = defaultdict(float)
            for line in journal_pl_lines:
                pl_totals[line.account_id] += line.balance

            bridge_totals = defaultdict(float)
            for line in journal_debt_lines:
                collected = collected_by_line.get(line.id)
                if collected:
                    bridge_totals[line.account_id.x_legal_bridge_account_id] += collected

            netting_line_vals = []
            for account, balance in pl_totals.items():
                if currency.is_zero(balance):
                    continue
                netting_line_vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": _("Neteo de Cierre Mensual %s", period_label),
                            "debit": -balance if balance < 0 else 0.0,
                            "credit": balance if balance > 0 else 0.0,
                        },
                    )
                )
            for account, collected in bridge_totals.items():
                if currency.is_zero(collected):
                    continue
                netting_line_vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": _(
                                "Neteo de Cierre Mensual (cobrado en el período) %s",
                                period_label,
                            ),
                            "debit": -collected if collected < 0 else 0.0,
                            "credit": collected if collected > 0 else 0.0,
                        },
                    )
                )
            for line in journal_open_debt_lines:
                residual = debt_residuals[line.id]
                netting_line_vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": line.account_id.id,
                            "partner_id": line.partner_id.id,
                            "name": _("Cierre por Resumen: %s", line.move_id.name),
                            "debit": -residual if residual < 0 else 0.0,
                            "credit": residual if residual > 0 else 0.0,
                            "x_origin_document_id": line.move_id.id,
                        },
                    )
                )

            netting_move = self.env["account.move"].create(
                {
                    "journal_id": journal.id,
                    "date": self.date_to,
                    "move_type": "entry",
                    "ref": _("Neteo de Cierre Mensual %s", period_label),
                    "x_is_summary_entry": True,
                    "line_ids": netting_line_vals,
                }
            )
            netting_move.action_post()
            netting_moves |= netting_move

            (journal_pl_lines | journal_debt_lines).write(
                {"x_summary_move_id": netting_move.id}
            )

            for line in journal_open_debt_lines:
                netting_line = netting_move.line_ids.filtered(
                    lambda nl, line=line: (
                        nl.account_id == line.account_id
                        and nl.partner_id == line.partner_id
                        and nl.x_origin_document_id == line.move_id
                    )
                )
                (line | netting_line).reconcile()

        legal_pl_totals = defaultdict(float)
        for line in pl_lines:
            legal_pl_totals[line.account_id] += line.balance

        legal_bridge_totals = defaultdict(float)
        for line in debt_lines:
            collected = collected_by_line.get(line.id)
            if collected:
                legal_bridge_totals[line.account_id.x_legal_bridge_account_id] += collected

        legal_line_vals = []
        for account, balance in legal_pl_totals.items():
            if currency.is_zero(balance):
                continue
            legal_line_vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": account.id,
                        "name": _("Resumen Global %s", period_label),
                        "debit": balance if balance > 0 else 0.0,
                        "credit": -balance if balance < 0 else 0.0,
                    },
                )
            )
        for account, collected in legal_bridge_totals.items():
            if currency.is_zero(collected):
                continue
            legal_line_vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": account.id,
                        "name": _("Cobrado en el Período %s", period_label),
                        "debit": collected if collected > 0 else 0.0,
                        "credit": -collected if collected < 0 else 0.0,
                    },
                )
            )
        for line in open_debt_lines:
            residual = debt_residuals[line.id]
            partner_name = line.partner_id.display_name or ""
            legal_line_vals.append(
                (
                    0,
                    0,
                    {
                        "account_id": line.account_id.x_legal_debt_account_id.id,
                        "partner_id": line.partner_id.id,
                        "name": f"{line.move_id.name} - {partner_name}",
                        "debit": residual if residual > 0 else 0.0,
                        "credit": -residual if residual < 0 else 0.0,
                        "x_origin_document_id": line.move_id.id,
                    },
                )
            )

        if not legal_line_vals:
            raise UserError(_("No hay montos para resumir en el período seleccionado."))

        summary_move = self.env["account.move"].create(
            {
                "journal_id": self.legal_journal_id.id,
                "date": self.date_to,
                "move_type": "entry",
                "ref": _("Refundición Mensual %s", period_label),
                "x_is_summary_entry": True,
                "line_ids": legal_line_vals,
            }
        )
        summary_move.action_post()

        # Se marca TODO comprobante con una línea de deuda resumida en este
        # cierre, no solo los que quedaron con saldo abierto: también el que
        # ya estaba cobrado/pagado antes del cierre necesita trazabilidad
        # hacia el asiento legal que absorbió su venta/impuesto.
        debt_lines.move_id.write({"x_closed_by_summary_move_id": summary_move.id})

        self.write(
            {
                "summary_move_id": summary_move.id,
                "netting_move_ids": [(6, 0, netting_moves.ids)],
            }
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
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
