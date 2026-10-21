from odoo import models


class GeneralLedgerReport(models.AbstractModel):
    _inherit = "report.account_financial_report.general_ledger"

    def _get_report_values(self, docids, data):
        self = self.with_context(
            ivess_only_summary_entries=bool(data.get("only_summary_entries"))
        )
        return super()._get_report_values(docids, data)

    def _create_account(self, account, acc_id, gen_led_data, rec_after_date_to_ids):
        account = super()._create_account(
            account, acc_id, gen_led_data, rec_after_date_to_ids
        )
        if self.env.context.get("ivess_only_summary_entries"):
            account["move_lines"] = self._ivess_collapse_summary_lines(
                account["move_lines"], gen_led_data[acc_id]["init_bal"]["balance"]
            )
        return account

    def _ivess_collapse_summary_lines(self, move_lines, init_balance):
        """Una única línea por asiento resumen dentro de la cuenta.

        Las líneas del mismo asiento resumen sobre la cuenta (puente más una
        por comprobante abierto) se muestran como el neto, y el saldo
        acumulado se recalcula.
        """
        summary_ids = set(
            self.env["account.move"]
            .browse({line["entry_id"] for line in move_lines})
            .filtered("x_is_summary_entry")
            .ids
        )
        currency = self.env.company.currency_id
        # Leyenda del asiento (con su período) para las cuentas cuyas líneas no
        # la traen, como la deuda por comprobante.
        summary_labels = {}
        for line in self.env["account.move.line"].search(
            [
                ("move_id", "in", list(summary_ids)),
                ("name", "=like", "Resumen Global%"),
            ]
        ):
            summary_labels.setdefault(line.move_id.id, line.name)
        groups = {}
        result = []
        for line in move_lines:
            if line["entry_id"] not in summary_ids:
                result.append(line)
                continue
            if line["entry_id"] not in groups:
                groups[line["entry_id"]] = []
                result.append(groups[line["entry_id"]])
            groups[line["entry_id"]].append(line)
        collapsed = []
        for item in result:
            if isinstance(item, dict) or len(item) == 1:
                collapsed.append(item if isinstance(item, dict) else item[0])
                continue
            merged = dict(item[0])
            net = currency.round(sum(ln["debit"] - ln["credit"] for ln in item))
            label = summary_labels.get(item[0]["entry_id"]) or item[0]["ref_label"]
            merged.update(
                {
                    "debit": net if net > 0 else 0.0,
                    "credit": -net if net < 0 else 0.0,
                    "bal_curr": sum(ln["bal_curr"] for ln in item),
                    "partner_id": False,
                    "partner_name": "",
                    "name": label,
                    "ref_label": label,
                    "rec_id": False,
                    "rec_name": "",
                }
            )
            collapsed.append(merged)
        balance = init_balance
        for line in collapsed:
            balance += line["debit"] - line["credit"]
            line["balance"] = balance
        return collapsed
