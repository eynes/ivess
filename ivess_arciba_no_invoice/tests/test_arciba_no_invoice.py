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

    def _create_order_with_retention(self, amount=2073456.0):
        order = self.env["account.payment.order"].create(
            {
                "partner_id": self.partner.id,
                "journal_id": self.journal.id,
                "type": "payment",
                "company_id": self.env.company.id,
                "date": self.date,
                "number": "0001-00000431",
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
                "base_amount": amount,
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
