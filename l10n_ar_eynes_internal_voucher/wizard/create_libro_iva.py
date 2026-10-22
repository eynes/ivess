from odoo import models


class LibroIVAExporterWizard(models.TransientModel):
    _inherit = 'libro.iva.exporter.wizard'

    def _exclude_internal_vouchers(self, invoices):
        """Internal vouchers must not appear in the Libro IVA Digital."""
        return invoices.filtered(
            lambda m: m.journal_id.fiscal_type != 'internal_voucher'
        )

    def create_sales_voucher_file(self, invoices):
        return super().create_sales_voucher_file(
            self._exclude_internal_vouchers(invoices)
        )

    def create_purchases_voucher_file(self, invoices):
        return super().create_purchases_voucher_file(
            self._exclude_internal_vouchers(invoices)
        )

    def create_sales_voucher_file_xlsx(self, invoices):
        return super().create_sales_voucher_file_xlsx(
            self._exclude_internal_vouchers(invoices)
        )

    def create_purchases_voucher_file_xlsx(self, invoices):
        return super().create_purchases_voucher_file_xlsx(
            self._exclude_internal_vouchers(invoices)
        )
