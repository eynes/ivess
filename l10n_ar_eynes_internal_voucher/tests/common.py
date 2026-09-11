from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInternalVoucherCommon(TransactionCase):
    """Common setup for the internal voucher tests.

    NOTE: this builds its own minimal fixtures instead of using Odoo's
    generic AccountTestInvoicingCommon/BaseCommon mixins on purpose: those
    create a company-independent partner and a brand-new "independent"
    company, and both paths currently crash in this codebase for reasons
    unrelated to this module (a res.partner creation hook that enforces
    company-consistency on accounting properties even for the
    company-less test partner, and stale account_reports data incompatible
    with newly created companies). Working around l10n_ar_eynes/environment
    issues is out of scope here, so tests stay self-contained on the
    already-configured current company.

    Provides one 'internal' and one 'internal_voucher' sale journal, plus
    helpers to create posted invoices and perceptions on them.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        cls.partner = cls.env['res.partner'].create(
            {
                'name': 'Internal Voucher Test Partner',
                'company_id': cls.company.id,
            }
        )
        cls.product = cls.env['product.product'].create(
            {
                'name': 'Internal Voucher Test Product',
                'company_id': cls.company.id,
                'categ_id': cls.env['product.category'].search(
                    [], limit=1
                ).id,
            }
        )

        cls.normal_journal = cls.env['account.journal'].create(
            {
                'name': 'Normal Test Journal',
                'code': 'NRM01',
                'type': 'sale',
                'fiscal_type': 'internal',
                'denomination': 'b',
                'company_id': cls.company.id,
                'currency_id': cls.env.ref('base.ARS').id,
                'due_date': fields.Date.to_date('2023-01-01'),
            }
        )
        cls.internal_voucher_journal = cls.env['account.journal'].create(
            {
                'name': 'Internal Voucher Test Journal',
                'code': 'IVT01',
                'type': 'sale',
                'fiscal_type': 'internal_voucher',
                'denomination': 'b',
                'company_id': cls.company.id,
                'currency_id': cls.env.ref('base.ARS').id,
                'due_date': fields.Date.to_date('2023-01-01'),
            }
        )

        cls.arba_tax = cls.env['account.tax'].create(
            {
                'name': 'Test ARBA Perception',
                'amount': 3.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'inform_arba': True,
                'retention_type': 'gross_income',
                'company_id': cls.company.id,
            }
        )
        cls.arciba_tax = cls.env['account.tax'].create(
            {
                'name': 'Test ARCIBA Perception',
                'amount': 3.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
                'inform_arciba': True,
                'company_id': cls.company.id,
            }
        )
        cls.income_account = cls.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1
        )

    @classmethod
    def _create_invoice(cls, journal, move_type='out_invoice'):
        # denomination is a compute field derived from journal_id.denomination,
        # set on the test journals in setUpClass (not settable per-invoice).
        invoice = cls.env['account.move'].create(
            {
                'move_type': move_type,
                'partner_id': cls.partner.id,
                'date': fields.Date.today(),
                'invoice_date': fields.Date.today(),
                'currency_id': cls.env.ref('base.ARS').id,
                'journal_id': journal.id,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            'product_id': cls.product.id,
                            'account_id': cls.income_account.id,
                            'quantity': 1.0,
                            'name': 'Internal voucher test product',
                            'price_unit': 1000.0,
                        },
                    )
                ],
            }
        )
        return invoice

    @classmethod
    def _create_perception(cls, invoice, tax, base=1000.0, amount=30.0):
        return cls.env['perception.tax.line'].create(
            {
                'name': tax.name,
                'invoice_id': invoice.id,
                'date': invoice.invoice_date,
                'base': base,
                'amount': amount,
                'perception_id': tax.id,
                'company_id': invoice.company_id.id,
                'partner_id': invoice.partner_id.id,
            }
        )
