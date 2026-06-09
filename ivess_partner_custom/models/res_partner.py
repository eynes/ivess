# -*- coding: utf-8 -*-
from collections import defaultdict
from odoo import models, fields, api


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
