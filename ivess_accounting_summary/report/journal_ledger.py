from odoo import models


class JournalLedgerReport(models.AbstractModel):
    _inherit = "report.account_financial_report.journal_ledger"

    def _get_moves_domain(self, wizard, journal_ids):
        domain = super()._get_moves_domain(wizard, journal_ids)
        if wizard.only_summary_entries:
            # Se listan los asientos resumen del Diario Legal. Los
            # comprobantes ya resumidos y los asientos de neteo de los
            # diarios operativos se ocultan: el resumen legal los reemplaza
            # y mostrarlos duplicaría la información.
            domain += [
                ("x_closed_by_summary_move_id", "=", False),
                ("line_ids", "not any", [("x_summary_move_id", "!=", False)]),
                "|",
                ("x_is_summary_entry", "=", False),
                ("journal_id.x_is_legal_journal", "=", True),
                (
                    "id",
                    "not in",
                    self.env["account.move"]._ivess_get_summarized_payment_ids(
                        [wizard.company_id.id]
                    ),
                ),
            ]
        return domain

    def _get_move_lines_data(self, ml, wizard, ml_taxes, auto_sequence, exigible):
        res = super()._get_move_lines_data(
            ml, wizard, ml_taxes, auto_sequence, exigible
        )
        # Débitos positivos y créditos negativos.
        res["total"] = ml.debit - ml.credit
        return res

    def _get_report_values(self, docids, data):
        res = super()._get_report_values(docids, data)
        wizard = res["docs"]
        for journal_ledger in res["Journal_Ledgers"]:
            journal_ledger["total"] = journal_ledger["debit"] - journal_ledger["credit"]
        # Los asientos de cada diario ya están en res["Moves"], así que el
        # total general no depende de la agrupación elegida.
        total_debit = total_credit = 0.0
        for move in res["Moves"]:
            for line in move["report_move_lines"]:
                total_debit += line["debit"]
                total_credit += line["credit"]
        if wizard.only_summary_entries:
            self._ivess_collapse_summary_moves(res["Moves"])
        res.update(
            {
                "hide_partner": wizard.hide_partner,
                "only_summary_entries": wizard.only_summary_entries,
                "fiscal_year_name": wizard._ivess_get_fiscal_year_name(),
                "period_text": wizard._ivess_get_period_text(),
                "grand_total": {
                    "debit": total_debit,
                    "credit": total_credit,
                    "total": total_debit - total_credit,
                },
            }
        )
        return res

    def _ivess_collapse_summary_moves(self, moves):
        """Una única línea por cuenta en los asientos resumen.

        El asiento resumen trae varias líneas sobre la misma cuenta (puente
        "cobrado en el período" más una línea por comprobante abierto). El
        libro legal muestra el neto por cuenta. Se muta la lista de líneas
        de cada asiento, que comparten los diarios y "Moves", así que los
        totales no cambian.
        """
        summary_ids = set(
            self.env["account.move"]
            .browse([move["move_id"] for move in moves])
            .filtered("x_is_summary_entry")
            .ids
        )
        currency = self.env.company.currency_id
        for move in moves:
            if move["move_id"] not in summary_ids:
                continue
            groups = {}
            for line in move["report_move_lines"]:
                groups.setdefault(line["account_id"], []).append(line)
            collapsed = []
            for lines in groups.values():
                if len(lines) == 1:
                    collapsed.append(lines[0])
                    continue
                merged = dict(lines[0])
                net = currency.round(sum(ln["debit"] - ln["credit"] for ln in lines))
                merged.update(
                    {
                        "debit": net if net > 0 else 0.0,
                        "credit": -net if net < 0 else 0.0,
                        "total": net,
                        "amount_currency": sum(ln["amount_currency"] for ln in lines),
                        "partner_id": False,
                        "label": next(
                            (
                                ln["label"]
                                for ln in lines
                                if (ln["label"] or "").startswith("Resumen Global")
                            ),
                            lines[0]["label"],
                        ),
                    }
                )
                collapsed.append(merged)
            move["report_move_lines"] = collapsed
