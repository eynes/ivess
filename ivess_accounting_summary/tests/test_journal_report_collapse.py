from odoo.tests import tagged

from .common import IvessAccountingSummaryTestCommon


@tagged("post_install", "-at_install")
class TestJournalReportCollapse(IvessAccountingSummaryTestCommon):
    def test_collapse_groups_flagged_account_lines(self):
        account = self.receivable_account
        account.x_summarize_on_report = True
        handler = self.env["account.journal.report.handler"]

        entries = [
            {
                "account_code": account.code,
                "partner_name": "Alfa",
                "name": "INV/001",
                "reference": "",
                "debit": 121000.0,
                "credit": 0.0,
                "balance": 121000.0,
            },
            {
                "account_code": account.code,
                "partner_name": "Beta",
                "name": "INV/002",
                "reference": "",
                "debit": 60500.0,
                "credit": 0.0,
                "balance": 60500.0,
            },
            {
                "account_code": "OTHER",
                "partner_name": False,
                "name": "Ventas",
                "reference": "",
                "debit": 0.0,
                "credit": 181500.0,
                "balance": -181500.0,
            },
        ]

        result = handler._ivess_collapse_summarized_accounts([entries])

        self.assertEqual(len(result), 1)
        collapsed_entries = result[0]
        # La cuenta no marcada se mantiene intacta; las dos líneas de la
        # cuenta marcada se colapsan en una sola.
        self.assertEqual(len(collapsed_entries), 2)

        collapsed = next(
            e for e in collapsed_entries if e["account_code"] == account.code
        )
        self.assertEqual(collapsed["partner_name"], "(Resumen Global)")
        self.assertEqual(collapsed["debit"], 181500.0)
        self.assertEqual(collapsed["credit"], 0.0)
        self.assertEqual(collapsed["balance"], 181500.0)

        untouched = next(e for e in collapsed_entries if e["account_code"] == "OTHER")
        self.assertEqual(untouched["credit"], 181500.0)

    def test_collapse_is_noop_without_flagged_accounts(self):
        handler = self.env["account.journal.report.handler"]
        entries = [
            {
                "account_code": "X",
                "partner_name": "Alfa",
                "name": "INV/001",
                "reference": "",
                "debit": 100.0,
                "credit": 0.0,
                "balance": 100.0,
            }
        ]

        result = handler._ivess_collapse_summarized_accounts([entries])

        self.assertEqual(result, [entries])
