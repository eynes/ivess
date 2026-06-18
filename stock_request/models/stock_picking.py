# Copyright 2017-2020 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_ids = fields.One2many(
        comodel_name="stock.request",
        string="Stock Requests",
        compute="_compute_stock_request_ids",
    )
    stock_request_count = fields.Integer(
        "Stock Request #", compute="_compute_stock_request_ids"
    )
    manual_location = fields.Boolean(readonly=True)

    @api.depends('picking_type_id', 'partner_id', 'manual_location')
    def _compute_location_id(self):
        manual_pickings = self.filtered(lambda p: p.manual_location)
        standard_pickings = self - manual_pickings
        if standard_pickings:
            super(StockPicking, standard_pickings)._compute_location_id()

    @api.depends("move_ids")
    def _compute_stock_request_ids(self):
        for rec in self:
            rec.stock_request_ids = rec.move_ids.mapped("stock_request_ids")
            rec.stock_request_count = len(rec.stock_request_ids)

    def action_view_stock_request(self):
        """
        :return dict: dictionary value for created view
        """
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_request.action_stock_request_form"
        )

        requests = self.mapped("stock_request_ids")
        if len(requests) > 1:
            action["domain"] = [("id", "in", requests.ids)]
        elif requests:
            action["views"] = [
                (self.env.ref("stock_request.view_stock_request_form").id, "form")
            ]
            action["res_id"] = requests.id
        return action
