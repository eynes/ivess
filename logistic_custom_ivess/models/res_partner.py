import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_customer = fields.Boolean(
        string='Es Cliente',
        compute='_compute_is_customer',
        inverse='_inverse_is_customer',
        store=True,
    )
    is_supplier = fields.Boolean(
        string='Es Proveedor',
        compute='_compute_is_supplier',
        inverse='_inverse_is_supplier',
        store=True,
    )
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
            ('discharge_review', 'Discharge Review'),
            ('holidays', 'Holidays'),
            ('inactive', 'Inactive'),
        ],
        default=False,
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
    qty_frio_calor = fields.Integer(
        'Qty equipos Frio/Calor',
        compute='_compute_qty_frio_calor',
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
    )
    partner_type_id = fields.Many2one(
        comodel_name="client.type",
        string="Partner Type",
    )
    registration_channel_id = fields.Many2one(
        comodel_name="registration.channel",
        string="Canal de Alta",
        tracking=True,
    )
    average_hour = fields.Float(
        string="Average Hour"
    )
    visit_hour_from = fields.Float(
        string="Horario de Visita Desde",
    )
    visit_hour_to = fields.Float(
        string="Horario de Visita Hasta",
    )
    is_important_client = fields.Boolean(
        string="Cliente Importante",
    )
    mobile_number = fields.Char(
        string="Numero de Celular",
    )
    address_details = fields.Text(
        string="Observaciones de Dirección",
    )

    @api.depends('customer_rank')
    def _compute_is_customer(self):
        for rec in self:
            rec.is_customer = rec.customer_rank > 0

    def _inverse_is_customer(self):
        for rec in self:
            if rec.is_customer and rec.customer_rank == 0:
                rec.customer_rank = 1
            elif not rec.is_customer:
                rec.customer_rank = 0

    @api.depends('supplier_rank')
    def _compute_is_supplier(self):
        for rec in self:
            rec.is_supplier = rec.supplier_rank > 0

    def _inverse_is_supplier(self):
        for rec in self:
            if rec.is_supplier and rec.supplier_rank == 0:
                rec.supplier_rank = 1
            elif not rec.is_supplier:
                rec.supplier_rank = 0

    def _assign_customer_code(self):
        for rec in self:
            if not rec.is_customer or rec.customer_code:
                continue
            company_id = rec.company_id.id or self.env.company.id
            sequence = self.env['ir.sequence'].search([
                ('code', '=', 'res.partner.ivess'),
                ('company_id', '=', company_id),
            ], limit=1)
            if sequence:
                rec.customer_code = sequence.next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._assign_customer_code()
        return records

    @api.constrains('visit_hour_from', 'visit_hour_to')
    def _check_visit_hour(self):
        for record in self:
            if not record.visit_hour_from and not record.visit_hour_to:
                continue
            if record.visit_hour_from < 7.0:
                raise ValidationError(_("El horario de visita debe comenzar a partir de las 07:00."))
            if record.visit_hour_to > 19.0:
                raise ValidationError(_("El horario de visita no puede finalizar después de las 19:00."))
            if record.visit_hour_from >= record.visit_hour_to:
                raise ValidationError(_("El horario 'Desde' debe ser anterior al horario 'Hasta'."))
            if record.visit_hour_to - record.visit_hour_from < 3.0:
                raise ValidationError(_("La diferencia entre el horario 'Desde' y 'Hasta' debe ser de al menos 3 horas."))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("The 'Date From' must be before or equal to 'Date To'."))

    @api.depends('water_container_ids', 'water_container_ids.is_frio_calor')
    def _compute_qty_containers(self):
        for rec in self:
            rec.qty_water_containers = len(rec.water_container_ids.filtered(lambda c: not c.is_frio_calor))

    @api.depends('water_container_ids', 'water_container_ids.is_frio_calor')
    def _compute_qty_frio_calor(self):
        for rec in self:
            rec.qty_frio_calor = len(rec.water_container_ids.filtered(lambda c: c.is_frio_calor))

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

    def write(self, vals):
        self._check_pending_water_containers_before_archiving(vals)

        if self.should_delete_related_lines(vals):
            self._delete_route_lines()
            self.empty_vals(vals)

        res = super().write(vals)

        if 'is_customer' in vals or 'customer_rank' in vals:
            self._assign_customer_code()

        if vals.get('active') is False:
            nonproductive = self.water_container_ids.filtered(lambda c: not c.is_nonproductive)
            if nonproductive:
                nonproductive.write({'is_nonproductive': True})
                for c in nonproductive:
                    c.message_post(body=_('Marcado como Improductivo: cliente dado de baja.'))

        return res

    def unlink(self):
        for partner in self:
            partner._check_pending_water_containers_before_archiving()
            partner._delete_route_lines()
            partner.distributions_ids.unlink()
        return super().unlink()

    def empty_vals(self, vals):
        vals.update({
            'distributions_ids': [(5, 0, 0)],
            'state': 'discharge_review',
        })
        return vals

    def _check_pending_water_containers_before_archiving(self, vals=None):
        if self.env.user.has_group('logistic_custom_ivess.group_allow_archive_debt_or_containers'):
            return

        if vals is None or vals.get('active') is False:
            unpaid_invoices = self.get_unpaid_invoice_count()

            errors = []
            if unpaid_invoices > 0:
                errors.append(_("This customer has %s unpaid or partially paid invoice(s).") % unpaid_invoices)

            if errors:
                raise UserError('\n'.join(errors))

    def get_unpaid_invoice_count(self):
        self.ensure_one()
        return self.env['account.move'].search_count([
            ('partner_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ])

    def should_delete_related_lines(self, vals):
        return (
            'active' in vals and vals['active'] is False
        ) or (
            'state' in vals and vals['state'] == 'discharge_review'
        )

    def _cron_check_partner_state(self):
        _logger.info("Cron - Checking partner states")
        today = fields.Date.today()

        domain = [('state', '=', 'holidays'), ('date_to', '<', today)]
        partners_to_update = self.search(domain)
        partners_to_update.write({'state': False, 'date_from': False, 'date_to': False})

        _logger.info(f">>>>>>>>>> Checked and updated {len(partners_to_update)} partners states")

    @api.model
    def _cron_check_partner_inactivity(self):
        _logger.info("Cron - Checking partner inactivity")
        thirty_days_ago = fields.Date.today() - timedelta(days=30)

        candidates = self.search([
            ('is_customer', '=', True),
            ('state', 'not in', ['holidays', 'discharge_review', 'inactive']),
        ])

        to_deactivate = self.env['res.partner']
        for partner in candidates:
            has_recent_sale = self.env['sale.order'].search_count([
                ('partner_id', '=', partner.id),
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', thirty_days_ago),
            ])
            if not has_recent_sale:
                to_deactivate |= partner

        if to_deactivate:
            to_deactivate.write({'state': 'inactive'})

        _logger.info(f">>>>>>>>>> Checked and marked {len(to_deactivate)} partners as inactive")

    def _delete_route_lines(self):
        for partner in self:
            today = fields.Date.today()
            delete_route_lines = partner.get_lines_to_delete(today)
            reason_msg = _("because was either archived or flagged as potentially inactive on %(date)s") % {
                'date': today.strftime("%d/%m/%Y")}
            delete_route_lines.with_context(chatter_note=reason_msg).unlink()

    def get_lines_to_delete(self, today):
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
        action['domain'] = [('partner_id', '=', self.id), ('is_frio_calor', '=', False)]
        action['context'] = {'default_partner_id': self.id}
        return action

    def action_open_frio_calor_containers(self):
        self.ensure_one()
        action = self.env.ref('logistic_custom_ivess.action_frio_calor_container').sudo().read()[0]
        action['domain'] = [('partner_id', '=', self.id), ('is_frio_calor', '=', True)]
        action['context'] = {'default_partner_id': self.id}
        return action

    def action_open_water_consumption(self):
        self.ensure_one()
        action = self.env.ref('logistic_custom_ivess.action_water_consumption').sudo().read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action
