from odoo import _, fields, models


class JournalLedgerReportWizard(models.TransientModel):
    _inherit = "journal.ledger.report.wizard"

    hide_partner = fields.Boolean(
        string="Ocultar socio",
        help="Oculta la columna Socio en el PDF, la vista y el Excel.",
    )
    only_summary_entries = fields.Boolean(
        string="Listar asientos resumen",
        help=(
            "Muestra los asientos resumen del Diario Legal y oculta los "
            "comprobantes que fueron resumidos por un Cierre Mensual (y sus "
            "asientos de neteo), para no duplicar información."
        ),
    )

    def _prepare_report_journal_ledger(self):
        res = super()._prepare_report_journal_ledger()
        res.update(
            {
                "hide_partner": self.hide_partner,
                "only_summary_entries": self.only_summary_entries,
            }
        )
        return res

    def _ivess_get_fiscal_year_name(self):
        """Nombre del ejercicio al que pertenece el período del wizard.

        Usa account.fiscal.year (si el modelo existe en la base) para el
        ejercicio que contiene la fecha de inicio; si no hay ninguno
        definido, cae al año de la fecha de fin.
        """
        self.ensure_one()
        if "account.fiscal.year" in self.env:
            fiscal_year = self.env["account.fiscal.year"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("date_from", "<=", self.date_from),
                    ("date_to", ">=", self.date_from),
                ],
                limit=1,
            )
            if fiscal_year:
                return fiscal_year.name
        return str(self.date_to.year)

    def _ivess_get_period_text(self):
        self.ensure_one()
        return _(
            "%(date_from)s A %(date_to)s",
            date_from=self.date_from.strftime("%d/%m/%Y"),
            date_to=self.date_to.strftime("%d/%m/%Y"),
        )
