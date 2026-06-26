# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api

FREQUENCY_MAPPING = {
    'weekly': 1,
    'biweekly': 2,
    'monthly': 4,
}


class PartnerDistributions(models.Model):
    _name = 'partner.distribution'
    _description = 'Distributions'

    distribution = fields.Many2one('template.delivery.route', tracking=True)
    visit_day = fields.Selection(
        related='distribution.day',
        string='Visit Day',
        tracking=True,
    )
    frequency = fields.Selection(
        selection=[
            ('weekly', 'Weekly'),
            ('biweekly', 'Biweekly'),
            ('monthly', 'Monthly')
        ],
        default=False,
        string='Frequency',
        tracking=True,
    )
    partner_id = fields.Many2one('res.partner', string='Partner', tracking=True)
    route_line_id = fields.Many2one(
        'delivery.route.line',
        string='Route Line',
        ondelete='set null',
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.distribution and record.partner_id:
                record._process_template_line()
                record._process_delivery_routes()
        return records

    def write(self, vals):
        old_vals = {
            rec.id: {
                'distribution': rec.distribution.id,
                'frequency': rec.frequency,
            }
            for rec in self
        }
        res = super().write(vals)
        if 'distribution' in vals or 'frequency' in vals:
            for record in self:
                old = old_vals[record.id]
                distribution_changed = 'distribution' in vals and (vals.get('distribution') or False) != old['distribution']
                frequency_changed = 'frequency' in vals

                if distribution_changed:
                    if old['distribution']:
                        self.env['delivery.route.line'].search([
                            ('template_route_id', '=', old['distribution']),
                            ('client_id', '=', record.partner_id.id),
                            ('route_id', '=', False),
                        ]).unlink()
                        record._unlink_future_route_lines(old['distribution'])
                    if record.distribution and record.partner_id:
                        record._process_template_line()
                        record._process_delivery_routes()
                elif frequency_changed and record.distribution:
                    record._unlink_future_route_lines(record.distribution.id)
                    record._process_delivery_routes()
        return res

    def unlink(self):
        for record in self:
            if record.distribution and record.partner_id:
                record._unlink_future_route_lines(record.distribution.id)
        route_lines = self.mapped('route_line_id')
        res = super().unlink()
        if not self.env.context.get('no_sync_distribution'):
            route_lines.with_context(no_sync_distribution=True).unlink()
        return res

    def _process_template_line(self):
        self.ensure_one()
        existing = self.distribution.delivery_route_line_ids.filtered(
            lambda l: l.client_id.id == self.partner_id.id and not l.route_id
        )
        if existing:
            self.route_line_id = existing[0].id
            return
        line = self.env['delivery.route.line'].create({
            'template_route_id': self.distribution.id,
            'client_id': self.partner_id.id,
        })
        self.route_line_id = line.id

    def _process_delivery_routes(self):
        self.ensure_one()
        if not self.distribution or not self.partner_id or not self.frequency:
            return

        today = fields.Date.today()
        filtered_routes = self.env['delivery.route'].search([
            ('delivery_date', '>', today),
            ('template_delivery_route_id', '=', self.distribution.id),
        ], order='delivery_date')
        route_dates = sorted(r.delivery_date for r in filtered_routes)

        monthly_dates = defaultdict(list)
        for date in route_dates:
            monthly_dates[date.strftime('%Y-%m')].append(date)

        interval = FREQUENCY_MAPPING.get(self.frequency, 1)
        if self.frequency == 'monthly':
            selected_dates = [dates[0] for dates in monthly_dates.values()]
        else:
            selected_dates = route_dates[::interval]

        for route in filtered_routes.filtered(lambda r: r.delivery_date in selected_dates):
            new_line = self.env['delivery.route.line'].create({'client_id': self.partner_id.id})
            route.delivery_route_line_ids = [(4, new_line.id)]

    def _unlink_future_route_lines(self, distribution_id):
        self.ensure_one()
        today = fields.Date.today()
        self.env['delivery.route.line'].search([
            ('client_id', '=', self.partner_id.id),
            ('route_id.delivery_date', '>', today),
            ('route_id.template_delivery_route_id', '=', distribution_id),
        ]).unlink()
