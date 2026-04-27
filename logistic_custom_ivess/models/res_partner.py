import logging

from dateutil.utils import today

from odoo import models, fields, _, api
from odoo.exceptions import ValidationError, UserError
from collections import defaultdict

_logger = logging.getLogger(__name__)

FREQUENCY_MAPPING = {
    'weekly': 1,
    'biweekly': 2,
    'monthly': 4,
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

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
    state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('discharge_review', 'Discharge Review'),
            ('dont_pass', "Don't pass"),
            ('holidays', 'Holidays'),
            ('rake', 'Rake')
        ],
        default='active',
        string='State',
        tracking=True,
    )
    date_from = fields.Date('Date From', tracking=True)
    date_to = fields.Date('Date To', tracking=True)
    water_container_ids = fields.One2many(
        'water.container',
        'partner_id',
        string="Water Containers"
    )
    qty_water_containers = fields.Integer(
        'Qty water containers',
        compute="_compute_qty_containers"
    )
    water_consumption_ids = fields.One2many(
        'res.partner.water.consumption',
        'partner_id',
        string="Water Consumption"
    )
    qty_water_consumption = fields.Integer(
        'Qty water consumption',
        compute="_compute_qty_consumption"
    )
    current_month_water_liters = fields.Float(
        'Current month water liters',
        compute='_compute_current_month_water_liters',
        store=True,
    )
    current_year_water_liters = fields.Float(
        'Current year water liters',
        compute='_compute_year_water_liters',
        store=True,
    )
    distributions_ids = fields.One2many(
        'partner.distribution',
        'partner_id',
        string='Distributions',
        tracking=True
    )
    customer_code = fields.Char(
        string="Customer Code",
        readonly=True,
        copy=False,
        compute="_compute_customer_code",
        store=True
    )
    partner_type_id = fields.Many2one(
        comodel_name="client.type",
        string="Partner Type",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('customer_rank', 0) >= 1:
                sequence = self.env.company.customer_sequence_id
                if sequence:
                    vals['customer_code'] = sequence.next_by_id()
        return super(ResPartner, self).create(vals_list)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("The 'Date From' must be before or equal to 'Date To'."))

    @api.depends('water_container_ids')
    def _compute_qty_containers(self):
        for rec in self:
            rec.qty_water_containers = len(rec.water_container_ids)

    @api.depends(
        'water_consumption_ids',
        'water_consumption_ids.consumption_liters',
        'water_consumption_ids.month',
        'water_consumption_ids.year',
    )
    def _compute_current_month_water_liters(self):
        today = fields.Date.today()
        for partner in self:
            record = partner.water_consumption_ids.filtered(
                lambda r: r.month == today.month and r.year == today.year
            )
            partner.current_month_water_liters = record.consumption_liters if record else 0.0

    @api.depends(
        'water_consumption_ids',
        'water_consumption_ids.consumption_liters',
        'water_consumption_ids.year',
    )
    def _compute_year_water_liters(self):
        today = fields.Date.today()
        for partner in self:
            record = partner.water_consumption_ids.filtered(
                lambda r: r.year == today.year
            )
            partner.current_year_water_liters = sum(record.mapped('consumption_liters')) if record else 0.0

    @api.depends('water_consumption_ids')
    def _compute_qty_consumption(self):
        for rec in self:
            rec.qty_water_consumption = len(rec.water_consumption_ids)

    @api.depends('customer_rank')
    def _compute_customer_code(self):
        for record in self:
            company_id = record.company_id.id or self.env.company.id
            sequence = self.env['ir.sequence'].search([
                ('code', '=', 'res.partner.ivess'),
                ('company_id', '=', company_id)
            ], limit=1)
            if sequence:
                record.customer_code = sequence.next_by_id()
            else:
                record.customer_code = "PENDIENTE"

    def _get_customer_sequence_vals(self):
        """
        Retorna un diccionario con el número de secuencia si corresponde.
        """
        self.ensure_one() # Nos aseguramos de procesar de a uno
        if self.customer_rank >= 1 and not self.customer_code:
            company = self.company_id or self.env.company
            seq_code = self.env['ir.sequence'].with_company(company).customer_sequence_id.next_by_id()
            if seq_code:
                return {'customer_code': seq_code}
        return {}

    def write(self, vals):
        old_distribution = {
            'distribution': self.distribution.id if self.distribution and 'distribution' in vals else None}

        self._check_pending_water_containers_before_archiving(vals)

        if self.should_delete_related_lines(vals):
            self._delete_route_lines()
            self.empty_vals(vals)

        # if 'customer_rank' in vals:
        #     sequence_vals = self._get_customer_sequence_vals()
        #     if sequence_vals:
        #         vals.update(sequence_vals)

        res = super().write(vals)

        if 'distribution' in vals or 'frequency' in vals:
            if vals.get('distribution'):
                self._process_new_template_delivery(vals.get('distribution'))
            if old_distribution.get('distribution'):
                self._process_old_template_delivery(old_distribution.get('distribution'))


            self._reprocess_delivery_routes(vals.get('distribution'), old_distribution.get('distribution'),
                                            vals.get('frequency'))

        return res

    def unlink(self):
        for partner in self:
            partner._check_pending_water_containers_before_archiving()
        return super().unlink()

    def empty_vals(self, vals):
        vals.update({
                'distribution': False,
                'visit_day': False,
                'frequency': False,
                'state': 'discharge_review',
            })
        return vals

    def _check_pending_water_containers_before_archiving(self, vals=None):
        """Valida si hay envases pendientes al intentar archivar o eliminar."""
        if self.env.user.has_group('logistic_custom_ivess.group_allow_archive_debt_or_containers'):
            return

        # Se ejecuta solo si se está desactivando el cliente (archivando)
        if vals is None or vals.get('active') is False:
            pending_containers = self.check_water_container()
            unpaid_invoices = self.get_unpaid_invoice_count()

            errors = []
            if pending_containers > 0:
                errors.append(_("This customer has %s water containers pending return.") % pending_containers)
            if unpaid_invoices > 0:
                errors.append(_("This customer has %s unpaid or partially paid invoice(s).") % unpaid_invoices)

            if errors:
                raise UserError('\n'.join(errors))

    def check_water_container(self):
        self.ensure_one()
        return self.env['water.container'].search_count(
            [
                ('partner_id', '=', self.id),
                ('state_id.is_pending_return', '=', True)
            ]
        )

    def get_unpaid_invoice_count(self):
        """Retorna la cantidad de facturas sin pagar o parcialmente pagadas del cliente."""
        self.ensure_one()
        return self.env['account.move'].search_count([
            ('partner_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ])

    def should_delete_related_lines(self, vals):
        """
        Evalúa si deben eliminarse líneas relacionadas basado en los valores escritos.
        Retorna:
            bool: True si active es False o si state es 'discharge_review'
        """
        return (
            'active' in vals and vals['active'] is False
        ) or (
            'state' in vals and vals['state'] == 'discharge_review'
        )

    def _process_new_template_delivery(self, distribution):
        TemplateDeliveryRoute = self.env['template.delivery.route']
        DeliveryRouteLine = self.env['delivery.route.line']

        template_id = TemplateDeliveryRoute.browse(distribution)
        existing_client = template_id.delivery_route_line_ids.filtered(lambda l: l.client_id.id == self.id)

        if not existing_client:
            new_line = DeliveryRouteLine.create({'client_id': self.id})
            template_id.delivery_route_line_ids = [(4, new_line.id)]

    def _process_old_template_delivery(self, distribution):
        DeliveryRouteLine = self.env['delivery.route.line']
        domain = [('template_route_id', '=', distribution), ('client_id', '=', self.id)]
        route_lines = DeliveryRouteLine.search(domain)
        if route_lines:
            route_lines.unlink()

    def _unlink_old_route_lines(self, today):
        DeliveryRouteLine = self.env['delivery.route.line']
        domain_route_line = [('route_id.delivery_date', '>', today),
                             ('client_id', '=', self.id)]
        filtered_routes_lines = DeliveryRouteLine.search(domain_route_line)
        filtered_routes_lines.unlink()

    def _reprocess_delivery_routes(self, distribution, old_distribution, frequency):
        DeliveryRouteLine = self.env['delivery.route.line']
        DeliveryRoute = self.env['delivery.route']
        today = fields.Date.today()

        if old_distribution or frequency:
            self._unlink_old_route_lines(today)

        if not distribution and not frequency:
            return

        distribution = distribution or self.distribution.id
        frequency = frequency or self.frequency

        domain_route = [('delivery_date', '>', today), ('template_delivery_route_id', '=', distribution)]
        filtered_routes = DeliveryRoute.search(domain_route, order="delivery_date")
        route_dates = sorted(route.delivery_date for route in filtered_routes)

        monthly_dates = defaultdict(list)
        for date in route_dates:
            monthly_dates[date.strftime("%Y-%m")].append(date)

        interval = FREQUENCY_MAPPING.get(frequency, 1)

        if frequency == 'monthly':
            selected_dates = [dates[0] for dates in monthly_dates.values()]
        else:
            selected_dates = route_dates[::interval]

        selected_routes = filtered_routes.filtered(lambda r: r.delivery_date in selected_dates)

        for route in selected_routes:
            new_line = DeliveryRouteLine.create({'client_id': self.id})
            route.delivery_route_line_ids = [(4, new_line.id)]


    def _cron_check_partner_state(self):
        _logger.info("Cron - Checking partner states")
        today = fields.Date.today()

        domain = [('state', 'in', ['holidays', 'dont_pass']), ('date_to', '<', today)]
        partners_to_update = self.search(domain)
        partners_to_update.write({'state': 'active', 'date_from': False, 'date_to': False})

        _logger.info(f">>>>>>>>>> Checked and updated {len(partners_to_update)} partners states")

    def _delete_route_lines(self):
        for partner in self:
            today = fields.Date.today()
            delete_route_lines = partner.get_lines_to_delete(today)
            reason_msg = _("because was either archived or flagged as potentially inactive on %(date)s") % {
                'date': today.strftime("%d/%m/%Y")}
            delete_route_lines.with_context(chatter_note=reason_msg).unlink()

    def get_lines_to_delete(self, today):
        """
            Obtiene las líneas de ruta (`delivery.route.line`) asociadas al partner que deberían ser eliminadas.

            Se consideran dos tipos de líneas:
            1. Líneas basadas en una ruta plantilla (`template_route_id`) que no tienen una ruta asignada (`route_id` vacío).
            2. Líneas asignadas a rutas cuya fecha de entrega (`delivery_date`) sea mayor o igual a la fecha actual.

            Returns:
                recordset: Un conjunto de registros de `delivery.route.line` que cumplen con los criterios anteriores.
        """
        DeliveryRouteLine = self.env['delivery.route.line']
        route_lines_template = DeliveryRouteLine.search([
                ('client_id', '=', self.id),
                ('template_route_id', '!=', False),
                ('route_id', '=', False),
            ])
        future_lines = DeliveryRouteLine.search([
            ('client_id', '=', self.id),
            ('route_id.delivery_date', '>=', today),
        ])
        return (route_lines_template | future_lines)

    def action_open_water_containers(self):
        self.ensure_one()
        action = self.env.ref('logistic_custom_ivess.action_water_container').sudo().read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

    def action_open_water_consumption(self):
        self.ensure_one()
        action = self.env.ref('logistic_custom_ivess.action_water_consumption').sudo().read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action
