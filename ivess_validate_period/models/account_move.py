from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        for move in self:
            period_info = move._validate_period()
            if period_info["invalid"]:
                if move.state == "draft" and period_info.get("suggested_date"):
                    move._adjust_date_and_propagate(period_info["suggested_date"])

                self.env.cr.commit()
                raise ValidationError(period_info["message"])
        return super()._post(soft=soft)

    def _adjust_date_and_propagate(self, new_date):
        self.ensure_one()
        self.date = new_date
        self._sync_payment_order_date(new_date)

    def _sync_payment_order_date(self, new_date):
        params = self.env.context.get("params", {})
        if params.get("model") == "account.payment.order" and params.get("id"):
            payment_order = self.env["account.payment.order"].browse(params["id"])
            if payment_order.exists() and payment_order.date != new_date:
                payment_order.date = new_date

    def _validate_period(self):
        self.ensure_one()
        date = self.date or self.invoice_date or fields.Date.context_today(self)
        journal_due_date = self.journal_id.due_date
        document_name = "%s (ID: %s)" % (self.display_name or _("(no name)"), self.id)

        if not journal_due_date:
            return {
                "invalid": True,
                "message": _(
                    "Document: %s\n"
                    "The journal does not have a closing date established.\n"
                    "Please configure it in: Accounting → Journals → Update journal periods."
                )
                % document_name,
            }

        if date < journal_due_date:
            suggested_date = journal_due_date + timedelta(days=1)
            return {
                "invalid": True,
                "message": _(
                    "Document: %s\n"
                    "The accounting date (%s) is earlier than the journal closing date (%s).\n"
                    "Autocorrecting to suggested date: %s.\n\n"
                    "PLEASE RELOAD THE PAGE TO SEE THE UPDATED DATE, OR TRY TO VALIDATE AGAIN — "
                    "THE NEW DATE WILL ALREADY BE USED."
                )
                % (
                    document_name,
                    date.strftime("%d-%m-%Y"),
                    journal_due_date.strftime("%d-%m-%Y"),
                    suggested_date.strftime("%d-%m-%Y"),
                ),
                "suggested_date": suggested_date,
            }

        return {"invalid": False}
