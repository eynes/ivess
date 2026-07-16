from odoo import models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _ensure_arba_a122r_activity_defaults(self):
        # Fix for duplicate-key error during _register_hook in l10n_ar_eynes.
        # The original method checks company.arba_a122r_activity_ids (ORM cache),
        # which may be stale at startup and not reflect rows already in the DB.
        # We filter via search_count (direct DB query) before delegating to super.
        Activity = self.env['res.company.arba.a122r.activity']
        companies_needing_defaults = self.filtered(
            lambda c: not Activity.search_count([('company_id', '=', c.id)])
        )
        if companies_needing_defaults:
            super(ResCompany, companies_needing_defaults)._ensure_arba_a122r_activity_defaults()
