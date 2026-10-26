from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import SQL


class AccountSummaryEngine(models.AbstractModel):
    """Lógica del Cierre Mensual compartida por el asistente (cierres chicos,
    en el momento) y el trabajo en segundo plano (cierres grandes, por tandas).

    Quien lo hereda debe tener company_id, date_from, date_to,
    operational_journal_ids, legal_journal_id, summary_move_date y
    summary_move_ref.
    """

    _name = "ivess.accounting.summary.engine"
    _description = "Motor del Cierre Mensual (Contabilidad Resumida)"

    @api.model
    def _summary_param(self, key, default):
        value = self.env["ir.config_parameter"].sudo().get_param(
            f"ivess_accounting_summary.{key}"
        )
        try:
            return int(value) if value else default
        except ValueError:
            return default

    @api.model
    def _summary_mark(self, records, field_name, move):
        """Apunta `field_name` (Many2one a account.move, sin cálculo ni
        validaciones propias) de `records` a `move` con un único UPDATE.

        Pasar por write() recorre las validaciones y los hooks de todos los
        módulos de contabilidad por cada lote, y para un simple marcador de
        trazabilidad eso era más de la mitad del tiempo del cierre."""
        if not records:
            return
        records.flush_recordset([field_name])
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = %s, write_uid = %s, write_date = NOW() AT TIME ZONE 'UTC' WHERE id = ANY(%s)",
                SQL.identifier(records._table),
                SQL.identifier(field_name),
                move.id,
                self.env.uid,
                records.ids,
            )
        )
        records.invalidate_recordset([field_name])

    @api.model
    def _summary_check_move_ids(self):
        """Ids de los asientos que tienen cheques (emitidos en sus líneas o
        de terceros depositados con ellos). Es un superconjunto de lo que
        l10n_ar_reconciliation revisa al conciliar: sin registros por
        compañía, de modo que nunca omite un asiento que sí tenga cheques."""
        cr = self.env.cr
        move_ids = set()
        if "issued_check_id" in self.env["account.move.line"]._fields:
            cr.execute(
                "SELECT DISTINCT move_id FROM account_move_line "
                "WHERE issued_check_id IS NOT NULL"
            )
            move_ids.update(row[0] for row in cr.fetchall())
        check_model = self.env.registry.get("account.check")
        if check_model is not None and "deposit_move_id" in check_model._fields:
            cr.execute(
                "SELECT DISTINCT deposit_move_id FROM account_check "
                "WHERE deposit_move_id IS NOT NULL"
            )
            move_ids.update(row[0] for row in cr.fetchall())
        return frozenset(move_ids)

    @api.model
    def _summary_entry_line_defaults(self):
        """Valores fijos para las líneas de los asientos que genera el cierre.

        La distribución analítica de una línea sale de los modelos de
        distribución; sin ninguno configurado siempre es vacía, y calcularla
        línea por línea (una búsqueda por contacto) es costo puro."""
        if self.env["account.analytic.distribution.model"].sudo().search_count(
            [], limit=1
        ):
            return {}
        return {"analytic_distribution": False}

    def _summary_period_label(self):
        return _(
            "%(date_from)s a %(date_to)s",
            date_from=self.date_from,
            date_to=self.date_to,
        )

    def _summary_candidate_domain(self):
        return [
            ("company_id", "=", self.company_id.id),
            ("journal_id", "in", self.operational_journal_ids.ids),
            ("move_id.state", "=", "posted"),
            ("move_id.x_is_summary_entry", "=", False),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("x_summary_move_id", "=", False),
        ]

    def _summary_candidate_lines(self, extra_domain=None, **search_kwargs):
        return self.env["account.move.line"].search(
            self._summary_candidate_domain() + (extra_domain or []),
            **search_kwargs,
        )

    def _summary_check_unmapped_debt_accounts(self, pl_lines):
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

    def _summary_close_lines(self, candidate_lines, label_suffix=""):
        """Netea en los diarios operativos las líneas dadas (que deben incluir
        todas las líneas de cada asiento) y las concilia con su neteo.

        :return: lo que aporta este lote al asiento resumen legal:
            {"netting_moves": account.move, "pl": {account_id: balance},
             "bridge": {account_id: {"amount": x, "payable": bool}},
             "debt": [{"account_id", "partner_id", "origin_id", "name",
                       "residual"}], "closed_move_ids": [ids]}
        """
        # Los asientos de neteo son asientos manuales: no hay líneas de
        # factura que sincronizar al crearlos, publicarlos ni conciliarlos.
        self = self.with_context(skip_invoice_sync=True)
        AccountMove = self.env["account.move"]
        AccountMoveLine = self.env["account.move.line"]

        # Las líneas sobre una cuenta de deudores/acreedores mapeada a una
        # cuenta legal son la "deuda" a trasladar; el resto son resultados
        # e impuestos a netear a cero en el diario operativo.
        debt_lines = candidate_lines.filtered(
            lambda line: line.account_id.x_legal_debt_account_id
        )
        pl_lines = candidate_lines - debt_lines
        self._summary_check_unmapped_debt_accounts(pl_lines)

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

        netting_moves = AccountMove
        line_defaults = self._summary_entry_line_defaults()
        period_label = self._summary_period_label()
        # Cada línea de deuda abierta se concilia contra su línea de neteo
        # (misma cuenta, contacto y comprobante de origen). Se indexa el
        # neteo una sola vez y se acumulan los grupos para conciliar todo
        # junto al final: buscar la línea de neteo con filtered() por cada
        # línea es cuadrático y reconcile() de a una pierde ~0,1 s cada vez.
        lines_by_key = defaultdict(lambda: AccountMoveLine)
        netting_lines_by_key = defaultdict(lambda: AccountMoveLine)

        for journal in self.operational_journal_ids & candidate_lines.journal_id:
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

            for _command, _unused, line_vals in netting_line_vals:
                line_vals.update(line_defaults)

            netting_move = AccountMove.create(
                {
                    "journal_id": journal.id,
                    "date": self.date_to,
                    "move_type": "entry",
                    "ref": _("Neteo de Cierre Mensual %s", period_label) + label_suffix,
                    "x_is_summary_entry": True,
                    "line_ids": netting_line_vals,
                }
            )
            netting_move.action_post()
            netting_moves |= netting_move

            self._summary_mark(
                journal_pl_lines | journal_debt_lines,
                "x_summary_move_id",
                netting_move,
            )

            netting_by_key = defaultdict(lambda: AccountMoveLine)
            for netting_line in netting_move.line_ids:
                if netting_line.x_origin_document_id:
                    netting_by_key[
                        (
                            netting_line.account_id.id,
                            netting_line.partner_id.id,
                            netting_line.x_origin_document_id.id,
                        )
                    ] |= netting_line
            for line in journal_open_debt_lines:
                key = (line.account_id.id, line.partner_id.id, line.move_id.id)
                lines_by_key[key] |= line
                netting_lines_by_key[key] |= netting_by_key[key]

        # Una sola conciliación en lote (un grupo por comprobante/contacto).
        AccountMoveLine.with_context(
            ivess_summary_check_move_ids=self._summary_check_move_ids()
        )._reconcile_plan(
            [lines_by_key[key] | netting_lines_by_key[key] for key in lines_by_key]
        )

        pl = defaultdict(float)
        for line in pl_lines:
            pl[line.account_id.id] += line.balance

        bridge = {}
        for line in debt_lines:
            collected = collected_by_line.get(line.id)
            if collected:
                bridge_account = line.account_id.x_legal_bridge_account_id
                entry = bridge.setdefault(
                    bridge_account.id, {"amount": 0.0, "payable": False}
                )
                entry["amount"] += collected
                entry["payable"] = line.account_id.account_type == "liability_payable"

        debt = []
        for line in open_debt_lines:
            partner_name = line.partner_id.display_name or ""
            debt.append(
                {
                    "account_id": line.account_id.x_legal_debt_account_id.id,
                    "partner_id": line.partner_id.id,
                    "origin_id": line.move_id.id,
                    "name": f"{line.move_id.name} - {partner_name}",
                    "residual": debt_residuals[line.id],
                }
            )

        return {
            "netting_moves": netting_moves,
            "pl": dict(pl),
            "bridge": bridge,
            "debt": debt,
            # Se marca TODO comprobante con una línea de deuda resumida en este
            # cierre, no solo los que quedaron con saldo abierto: también el que
            # ya estaba cobrado/pagado antes del cierre necesita trazabilidad
            # hacia el asiento legal que absorbió su venta/impuesto.
            "closed_move_ids": debt_lines.move_id.ids,
        }

    def _summary_legal_line_vals(self, pl, bridge, debt, only_totals=False, only_debt=False):
        """Líneas del asiento resumen legal a partir de lo que aportaron los
        lotes: resultados y puente agregados por cuenta, y una línea por cada
        deuda abierta."""
        currency = self.company_id.currency_id
        period_label = self._summary_period_label()
        vals = []
        if not only_debt:
            for account_id, balance in pl.items():
                if currency.is_zero(balance):
                    continue
                vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account_id,
                            "name": _("Resumen Global %s", period_label),
                            "debit": balance if balance > 0 else 0.0,
                            "credit": -balance if balance < 0 else 0.0,
                        },
                    )
                )
            for account_id, entry in bridge.items():
                collected = entry["amount"]
                if currency.is_zero(collected):
                    continue
                vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account_id,
                            # Proveedores pagados: misma leyenda que la línea de gastos.
                            "name": (
                                _("Resumen Global %s", period_label)
                                if entry["payable"]
                                else _("Cobrado en el Período %s", period_label)
                            ),
                            "debit": collected if collected > 0 else 0.0,
                            "credit": -collected if collected < 0 else 0.0,
                        },
                    )
                )
        if not only_totals:
            for item in debt:
                residual = item["residual"]
                vals.append(
                    (
                        0,
                        0,
                        {
                            "account_id": item["account_id"],
                            "partner_id": item["partner_id"],
                            "name": item["name"],
                            "debit": residual if residual > 0 else 0.0,
                            "credit": -residual if residual < 0 else 0.0,
                            "x_origin_document_id": item["origin_id"],
                        },
                    )
                )
        line_defaults = self._summary_entry_line_defaults()
        for _command, _unused, line_vals in vals:
            line_vals.update(line_defaults)
        return vals

    def _summary_move_vals(self, line_ids):
        return {
            "journal_id": self.legal_journal_id.id,
            "date": self.summary_move_date or self.date_to,
            "move_type": "entry",
            "ref": self.summary_move_ref
            or _("Refundición Mensual %s", self._summary_period_label()),
            "x_is_summary_entry": True,
            "line_ids": line_ids,
        }
