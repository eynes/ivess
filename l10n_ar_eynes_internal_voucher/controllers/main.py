from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.l10n_ar_eynes.controllers.main import (
    PortalAccount as L10nArEynesPortalAccount,
)


class PortalAccount(L10nArEynesPortalAccount):
    @http.route(
        ['/my/invoices/<int:invoice_id>'],
        type='http',
        auth="public",
        website=True,
    )
    def portal_my_invoice_detail(
        self,
        invoice_id,
        access_token=None,
        report_type=None,
        download=False,
        **kw
    ):
        try:
            invoice_sudo = self._document_check_access(
                'account.move', invoice_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
            report_name = 'l10n_ar_eynes.account_move_report'
            if invoice_sudo.fiscal_type in ('internal', 'internal_voucher'):
                report_name = 'account.account_invoices'
            return self._show_report(
                model=invoice_sudo,
                report_type=report_type,
                report_ref=report_name,
                download=download,
            )

        values = self._invoice_get_page_view_values(
            invoice_sudo, access_token, **kw
        )
        return request.render("account.portal_invoice_page", values)
