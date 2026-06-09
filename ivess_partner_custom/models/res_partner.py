# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    unbilled_balance = fields.Monetary(
        string="Unbilled Balance",
        compute="_compute_balances",
        store=True,
    )
    final_balance = fields.Monetary(
        string="Final Balance",
        compute="_compute_balances",
        store=True,
    )

    @api.depends(
        "sale_order_ids",
        "sale_order_ids.invoice_status",
        "sale_order_ids.invoice_ids",
        "sale_order_ids.invoice_ids.state",
        "sale_order_ids.invoice_ids.payment_state",
        "sale_order_ids.amount_total",
        "sale_order_ids.state",
    )
    def _compute_balances(self):
        payments_data = self.env["account.payment.order"].search_read(
            domain=[
                ("partner_id", "in", self.ids),
                ("state", "=", "posted"),
                ("type", "=", "receipt"),
            ],
            fields=["partner_id", "amount"],
        )
        payment_totals = defaultdict(float)
        for payment in payments_data:
            payment_totals[payment["partner_id"][0]] += payment["amount"]

        for partner in self:
            unbilled = 0.0
            total_orders = 0.0
            confirmed_orders = partner.sale_order_ids.filtered(
                lambda s: s.state in ["sale", "done"]
            )
            for order in confirmed_orders:
                total_orders += order.amount_total
                if order.invoice_status == "to invoice":
                    unbilled += order.amount_total

            partner.unbilled_balance = unbilled
            partner.final_balance = total_orders - payment_totals.get(partner.id, 0.0)

    def write(self, vals):
        self._check_pending_water_containers_before_archiving(vals)
        return super().write(vals)

    def unlink(self):
        for partner in self:
            partner._check_pending_water_containers_before_archiving()
        return super().unlink()

    def _check_pending_water_containers_before_archiving(self, vals=None):
        """Valida si hay envases pendientes al intentar archivar o eliminar."""
        if self.env.user.has_group('logistic_custom_ivess.group_allow_archive_debt_or_containers'):
            return

        if vals is None or vals.get('active') is False:
            errors = []
            for partner in self:
                pending = partner.check_water_container()
                unpaid = partner.get_unpaid_invoice_count()
                if pending > 0:
                    errors.append(_("This customer has %s water containers pending return.") % pending)
                if unpaid > 0:
                    errors.append(_("This customer has %s unpaid or partially paid invoice(s).") % unpaid)
            if errors:
                raise UserError('\n'.join(errors))

    def check_water_container(self):
        self.ensure_one()
        containers = self.env['water.container'].search([
            ('partner_id', '=', self.id),
        ])
        return sum(containers.mapped('quantity'))

    def get_unpaid_invoice_count(self):
        self.ensure_one()
        return self.env['account.move'].search_count([
            ('partner_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ])
