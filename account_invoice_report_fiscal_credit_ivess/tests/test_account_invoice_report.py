from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAccountInvoiceReportFiscalCredit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["account.invoice.report"]
        # Datos mínimos propios (cuentas, diario y proveedor): no se usa
        # AccountTestInvoicingCommon porque crea productos y custom_ivess_product
        # exige secuencias por categoría de producto.
        Account = cls.env["account.account"]
        cls.expense_account = Account.create(
            {"name": "Gasto crédito fiscal", "code": "9FC001", "account_type": "expense"}
        )
        payable_account = Account.create(
            {
                "name": "A pagar crédito fiscal",
                "code": "9FC002",
                "account_type": "liability_payable",
                "reconcile": True,
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        ) or cls.env["account.journal"].create(
            {"name": "Compras crédito fiscal", "code": "9FCC", "type": "purchase"}
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Proveedor crédito fiscal",
                "property_account_payable_id": payable_account.id,
            }
        )

    def _create_bill(self, move_type, fiscal_credits):
        """Factura con una línea por cada valor de crédito fiscal."""
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner.id,
                "journal_id": self.journal.id,
                "invoice_date": "2026-10-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Línea %d" % index,
                            "account_id": self.expense_account.id,
                            "quantity": 1,
                            "price_unit": 100.0 + index,
                            "fiscal_credit": fiscal_credit,
                        }
                    )
                    for index, fiscal_credit in enumerate(fiscal_credits)
                ],
            }
        )

    def test_selection_matches_move_line(self):
        """Los valores del reporte son los de account.move.line.fiscal_credit."""
        report_values = {
            value for value, _label in self.report._fields["fiscal_credit"].selection
        }
        line_values = {
            value
            for value, _label in self.env["account.move.line"]
            ._fields["fiscal_credit"]
            .selection
        }
        self.assertEqual(report_values, line_values)

    def test_report_exposes_line_fiscal_credit(self):
        """El reporte trae el crédito fiscal de cada línea de la factura de
        proveedor."""
        bill = self._create_bill(
            "in_invoice", ["direct_taxed", "direct_exempt", "apport"]
        )
        rows = self.report.search([("move_id", "=", bill.id)])
        self.assertEqual(
            sorted(rows.mapped("fiscal_credit")),
            sorted(["direct_taxed", "direct_exempt", "apport"]),
        )

    def test_group_by_fiscal_credit(self):
        """Se puede agrupar por crédito fiscal."""
        bill = self._create_bill("in_invoice", ["direct_taxed", "apport", "apport"])
        groups = self.report._read_group(
            [("move_id", "=", bill.id)],
            groupby=["fiscal_credit"],
            aggregates=["__count"],
        )
        self.assertEqual(
            {fiscal_credit: count for fiscal_credit, count in groups},
            {"direct_taxed": 1, "apport": 2},
        )

    def test_line_without_fiscal_credit_is_empty(self):
        """Una línea sin crédito fiscal figura sin valor en el reporte."""
        bill = self._create_bill("in_invoice", [False])
        rows = self.report.search([("move_id", "=", bill.id)])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.fiscal_credit)
