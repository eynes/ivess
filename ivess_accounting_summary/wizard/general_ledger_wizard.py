from odoo import fields, models


class GeneralLedgerReportWizard(models.TransientModel):
    _inherit = "general.ledger.report.wizard"

    only_summary_entries = fields.Boolean(
        string="Listar asientos resumen",
        help=(
            "Incluye los asientos resumen del Diario Legal y oculta los "
            "comprobantes que fueron resumidos por un Cierre Mensual, sus "
            "asientos de neteo y los cobros/pagos que ese cierre ya absorbió, "
            "para no duplicar información. Aplica a los movimientos del "
            "período y a los saldos iniciales; el asiento resumen sale con "
            "una única línea por cuenta (sin agrupar por contacto)."
        ),
    )

    def _get_account_move_lines_domain(self):
        domain = super()._get_account_move_lines_domain()
        if self.only_summary_entries:
            # Mismo criterio que el Libro Diario: el resumen legal reemplaza
            # a los comprobantes resumidos y a los asientos de neteo de los
            # diarios operativos. Este dominio lo usan tanto los movimientos
            # del período como los saldos iniciales y el Excel.
            domain = list(domain) + [
                (
                    "move_id",
                    "any",
                    [
                        ("x_closed_by_summary_move_id", "=", False),
                        (
                            "line_ids",
                            "not any",
                            [("x_summary_move_id", "!=", False)],
                        ),
                        "|",
                        ("x_is_summary_entry", "=", False),
                        ("journal_id.x_is_legal_journal", "=", True),
                    ],
                ),
                (
                    "move_id",
                    "not in",
                    self.env["account.move"]._ivess_get_summarized_payment_ids(
                        [self.company_id.id]
                    ),
                ),
            ]
        return domain

    def _prepare_report_general_ledger(self):
        res = super()._prepare_report_general_ledger()
        if self.only_summary_entries:
            # El asiento resumen se muestra con una única línea por cuenta:
            # agrupar por contacto lo volvería a abrir.
            res.update({"grouped_by": "none", "only_summary_entries": True})
        return res
