from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArcibaNoInvoice(TransactionCase):
    """[T16864] eARCIBA: retenciones de OP sin facturas (pago a cuenta)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Payment T16864",
                "type": "payment",
                "code": "P6864",
                "company_id": company.id,
                "currency_id": cls.env.ref("base.ARS").id,
                "due_date": fields.Date.to_date("2023-01-01"),
                "default_account_id": cls.env["account.account"]
                .search(
                    [
                        ("account_type", "=", "expense"),
                        ("company_ids", "in", company.id),
                    ],
                    limit=1,
                )
                .id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Proveedor Pago a Cuenta",
                "vat": "30-71234567-1",
                "document_type_id": cls.env.ref("l10n_ar_eynes.document_cuit").id,
            }
        )
        cls.retention = cls.env["account.tax"].create(
            {
                "name": "Ret IIBB T16864",
                "type_tax_use": "purchase",
                "amount_type": "percent",
                "amount": 0,
                "inform_arciba": True,
                "retention_type": "gross_income",
            }
        )
        cls.date = fields.Date.to_date("2026-09-25")
        cls.period = fields.Date.to_date("2026-09-01")
        cls.env["res.partner.retention"].create(
            {
                "partner_id": cls.partner.id,
                "retention_id": cls.retention.id,
                "period": cls.period,
                "percent": 4.5,
                "sit_iibb": cls.env.ref("l10n_ar_eynes.iibb_situation_local").id,
            }
        )

    @classmethod
    def _next_number(cls):
        cls._op_number = getattr(cls, "_op_number", 90000) + 1
        return cls._op_number

    def _create_order_with_retention(
        self,
        amount=2073456.0,
        partner=None,
        retention_amount=70686.0,
        base_amount=None,
    ):
        order = self.env["account.payment.order"].create(
            {
                "partner_id": (partner or self.partner).id,
                "journal_id": self.journal.id,
                "type": "payment",
                "company_id": self.env.company.id,
                "date": self.date,
                "number": f"0001-{self._next_number():08d}",
                # Evita que el sistema genere retenciones por adelanto.
                "disable_retentions": True,
                # Total de la OP = medios de pago + retenciones.
                "payment_mode_line_ids": [
                    (
                        0,
                        0,
                        {
                            "payment_mode_id": self.journal.id,
                            "amount": amount - 70686.0,
                        },
                    )
                ],
            }
        )
        retention_line = self.env["account.payment.order.retention.line"].create(
            {
                "payment_order_id": order.id,
                "retention_id": self.retention.id,
                "account_id": self.env["account.account"]
                .search(
                    [
                        ("account_type", "=", "liability_current"),
                        ("company_ids", "in", self.env.company.id),
                    ],
                    limit=1,
                )
                .id,
                "date": self.date,
                "name": self.retention.name,
                "base": 1570800.0,
                "base_amount": base_amount or amount,
                "amount": 70686.0,
                "certificate_no": "147",
            }
        )
        return order, retention_line

    def test_retention_without_invoices_is_exported(self):
        """Pago a cuenta: la retencion se informa en vez de dar error."""
        order, retention_line = self._create_order_with_retention()
        self.assertFalse(order.debt_line_ids)
        self.assertEqual(order.amount, 2073456.0)
        wizard = self.env["create.arciba.files"].create(
            {
                "company_id": self.env.company.id,
                "period_start": self.period,
                "period_end": fields.Date.to_date("2026-09-30"),
            }
        )

        status, result = wizard._get_ret_data([retention_line.id])

        self.assertIsNone(status, result)
        self.assertEqual(len(result), 1)
        line = result[0]
        self.assertEqual(line["type"], 1)
        self.assertEqual(line["nro_cert_propio"], "147")
        # Sin lineas de deuda el comprobante vale lo que la OP.
        self.assertEqual(line["monto_comprobante"].lstrip("0"), "2073456,00")
        # Sin facturas no hay IVA ni letra de comprobante.
        self.assertEqual(line["letra_comprobante"], "")

    def _create_wizard(self):
        return self.env["create.arciba.files"].create(
            {
                "company_id": self.env.company.id,
                "period_start": self.period,
                "period_end": fields.Date.to_date("2026-09-30"),
            }
        )

    def test_retention_without_padron_is_left_out_with_a_warning(self):
        """Sin padron la retencion se omite como siempre, pero se avisa."""
        _order, ok_line = self._create_order_with_retention(base_amount=1570800.0)
        no_padron = self.env["res.partner"].create(
            {
                "name": "Proveedor Sin Padron",
                "vat": "30-71234567-1",
                "document_type_id": self.env.ref("l10n_ar_eynes.document_cuit").id,
            }
        )
        _order2, no_padron_line = self._create_order_with_retention(
            partner=no_padron, base_amount=1570800.0
        )
        wizard = self._create_wizard()

        status, result = wizard._get_ret_data([ok_line.id, no_padron_line.id])

        self.assertIsNone(status)
        self.assertEqual(len(result), 1)
        self.assertIn("left out of the file", wizard.notes)
        self.assertIn("Retentions informed: 1/2", wizard.notes)

    def test_rate_mismatch_is_a_warning_and_content_is_unchanged(self):
        """Alicuota que no cierra con el importe: avisa, pero informa igual."""
        _order, retention_line = self._create_order_with_retention()
        wizard = self._create_wizard()

        status, result = wizard._get_ret_data([retention_line.id])

        self.assertIsNone(status)
        self.assertEqual(len(result), 1)
        # Lo informado es lo de siempre: alicuota del padron y base_amount.
        self.assertEqual(result[0]["alicuota"].lstrip("0"), "4,50")
        self.assertEqual(result[0]["monto_sujeto_a_ret_per"].lstrip("0"), "2073456,00")
        # 70.686 sobre 2.073.456 = 3,41%, la retencion se calculo sobre 1.570.800
        self.assertIn("4.50%", wizard.notes)
        self.assertIn("3.41%", wizard.notes)
        self.assertIn("1570800.00", wizard.notes)

    def test_consistent_retention_has_no_warnings(self):
        """Con padron y base consistentes no hay avisos."""
        _order, retention_line = self._create_order_with_retention(
            base_amount=1570800.0
        )
        wizard = self._create_wizard()

        status, result = wizard._get_ret_data([retention_line.id])

        self.assertIsNone(status)
        self.assertFalse(wizard.notes)
        self.assertEqual(len(result), 1)
