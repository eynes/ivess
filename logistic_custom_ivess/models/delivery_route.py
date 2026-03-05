from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)

class DeliveryRoute(models.Model):
    _name = 'delivery.route'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Delivery Route'
    _rec_name = 'name'

    # @api.onchange('delivery_person_id', 'truck_id')
    # def _onchange_delivery_person_id(self):
    #     if self.delivery_person_id and self.truck_id:
    #         if self.delivery_person_id not in self.truck_id.user_assigned_ids:
    #             self.delivery_person_id = False
    #             raise ValidationError(_("The delivery driver is not among the users assigned to this truck."))

    #     if self.delivery_route_line_ids and not self.create_from_wizard:
    #         self.delivery_route_line_ids.unlink()

    name = fields.Char(
        string="Name"
    )
    truck_id = fields.Many2one(
        'fleet.vehicle',
        string='Truck License Plate',
        # domain="allowed_truck_domain"
        # required=True
    )
    template_delivery_route_id = fields.Many2one(
        'template.delivery.route',
        string="Template delivery route",
    )
    delivery_person_id = fields.Many2one(
        'res.users',
        string='Delivery Person',
        # domain="allowed_person_domain",
        # required=True
    )
    # allowed_person_domain = fields.Binary(compute='_compute_allowed_person')
    # allowed_truck_domain = fields.Binary(compute='_compute_allowed_truck')
    delivery_date = fields.Date(
        string='Delivery Date',
    )
    delivery_route_line_ids = fields.One2many(
        'delivery.route.line',
        'route_id',
        string='Clients to Visit'
    )
    delivery_type = fields.Selection(
        selection=[('universal', 'Universal'), ('common', 'Common')],
        string='Type',
        default='common',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('closed', 'Closed')
        ],
        string='State',
        default='draft',
        tracking=True
    )
    create_from_wizard = fields.Boolean(
        string='Create from wizard',
    )
    delivery_number_id = fields.Many2one(
        string="Delivery route number",
        related="template_delivery_route_id.delivery_number_id",
        # required=True,
        store=True,
        tracking=True,
    )
    allow_price_editing = fields.Boolean(
        string="Allow Price Editing",
        related="template_delivery_route_id.allow_price_editing",
        store=True,
    )
    allow_reordering = fields.Boolean(
        string="Allow reordering",
        related="template_delivery_route_id.allow_reordering",
        store=True,
    )
    allow_closing_with_rake = fields.Boolean(
        string="Allow closing with rake",
        related="template_delivery_route_id.allow_closing_with_rake",
        store=True,
    )
    allow_cash_sale = fields.Boolean(
        string='Allow Cash Sale',
        related="template_delivery_route_id.allow_cash_sale",
        store=True,
        tracking=True,
        help="Reflects the cash‑sale setting of the associated delivery number."
    )
    allow_manual_address = fields.Boolean(
        string='Allow Manual Address',
        related="template_delivery_route_id.allow_manual_address",
        store=True,
        tracking=True,
        # help="Reflects the cash‑sale setting of the associated delivery number."
    )

    # @api.depends('truck_id')
    # def _compute_allowed_person(self):
    #     for rec in self:
    #         if rec.truck_id:
    #             domain = [('id', 'in', rec.truck_id.user_assigned_ids.ids)]
    #         else:
    #             domain = []
    #         rec.allowed_person_domain = domain

    # @api.depends('delivery_person_id')
    # def _compute_allowed_truck(self):
    #     for rec in self:
    #         if rec.delivery_person_id:
    #             domain = [('user_assigned_ids', 'in', rec.delivery_person_id.id)]
    #         else:
    #             domain = []
    #         rec.allowed_truck_domain = domain

    @api.onchange('template_delivery_route_id')
    def _onchange_template_delivery_route_id(self):
        if self.template_delivery_route_id:
            self.truck_id = self.template_delivery_route_id.truck_id
            # self.allow_price_editing = self.template_delivery_route_id.allow_price_editing
            # self.allow_reordering = self.template_delivery_route_id.allow_reordering

    def _prepare_route_lines_from_template(self, template):
        """Prepara las líneas de la ruta copiándolas desde el template."""
        return [(0, 0, {
            'route_id': self.id,
            'client_id': line.client_id.id,
        }) for line in template.delivery_route_line_ids]

    @api.model
    def create(self, vals):
        context = self.env.context
        if vals.get('template_delivery_route_id') and not context.get('create_from_wizard'):
            template = self.env['template.delivery.route'].browse(vals['template_delivery_route_id'])
            vals['delivery_route_line_ids'] = self._prepare_route_lines_from_template(template)
        return super().create(vals)

    def write(self, vals):
        for record in self:
            if 'template_delivery_route_id' in vals:
                if vals['template_delivery_route_id']:
                    template = self.env['template.delivery.route'].browse(vals['template_delivery_route_id'])
                    vals['delivery_route_line_ids'] = [(5, 0, 0)] + self._prepare_route_lines_from_template(template)
                else:
                    vals['truck_id'] = False
                    vals['delivery_route_line_ids'] = [(5, 0, 0)]  # Borra las líneas si se borra el template
        return super().write(vals)

    # def check_delivery_person(self):
    #     if self.delivery_person_id and self.truck_id:
    #         user = self.delivery_person_id
    #         return user not in self.truck_id.user_assigned_ids
    #     return False

    def action_set_in_progress(self):
        # if not self.delivery_route_line_ids:
        #     raise UserError(_('To start the route, you should first assign clients to visit.'))
        if not self.delivery_date:
            raise UserError(_("To start a delivery route, you must first set the delivery date."))
        self.state = 'in_progress'

    def action_set_closed(self):
        for record in self:
            record._validate_state()
            record._validate_rake_restriction()
        self.write({'state': 'closed'})

    def _validate_state(self):
        if self.state != 'in_progress':
            raise ValidationError("Solo se pueden cerrar registros en estado 'En Progreso'.")

    def _validate_rake_restriction(self):
        if not self.allow_closing_with_rake:
            rake_partners = self.delivery_route_line_ids.mapped('client_id').filtered(lambda p: p.state == 'rake')
            rake_reasons = self.delivery_route_line_ids.mapped('no_purchase_reason_id').filtered(
                lambda r: r.is_rake
            )
            if rake_partners or rake_reasons:
                msg_lines = []
                if rake_partners:
                    names = ', '.join(rake_partners.mapped('name'))
                    msg_lines.append(_("Clients in 'Rake' state: %s") % names)
                if rake_reasons:
                    lines_info = ', '.join(
                        '%s (%s)' % (l.client_id.name, l.no_purchase_reason_id.reason)
                        for l in self.delivery_route_line_ids
                        if l.no_purchase_reason_id and l.no_purchase_reason_id.is_rake
                    )
                    msg_lines.append(_("Non-purchase reasons marked as 'Rake' in the following lines: %s") % lines_info)

                full_msg = _("The record cannot be closed due to the following:") + "\n- " + "\n- ".join(msg_lines)
                raise ValidationError(full_msg)

    def action_reset_to_draft(self):
        self.delivery_route_line_ids.write({
            'visit_status_id': False,
            'no_purchase_reason_id': False,
        })
        self.state = 'draft'

    @api.model
    def cron_generate_routes_from_templates(self):
        """Crea rutas automáticamente para cada plantilla activa usando el wizard."""
        _logger.info("Cron - Generación automática de rutas de reparto el 1 de cada mes")
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=31)).replace(day=1)
        month_end = next_month - timedelta(days=1)

        templates = self.env['template.delivery.route'].search([])

        for template in templates:
            if not template.delivery_route_line_ids:
                continue
            wizard = self.env['delivery.route.mass.create.wizard'].create({
                'date_from': month_start,
                'date_to': month_end,
                'template_delivery_route_id': template.id,
            })
            wizard.action_generate_routes()

class DeliveryRouteLine(models.Model):
    _name = 'delivery.route.line'
    _description = 'Delivery Route Line'

    route_id = fields.Many2one(
        'delivery.route',
        string='Delivery Route',
        # required=True,
        ondelete='cascade',
        copy=False,
    )
    template_route_id = fields.Many2one(
        'template.delivery.route',
        string='Template Delivery Route',
        # required=True,
        ondelete='cascade',
        copy=False,
    )
    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True
    )
    customer_code = fields.Char(
        related="client_id.customer_code",
        store=True,
        readonly=True,
    )
    client_address = fields.Char(
        compute="_compute_address_client_id",
        string="Address",
        readonly=True,
        store=True,
    )
    visit_status_id = fields.Many2one(
        'visit.status',
        string='Visit Status',
    )
    no_purchase_reason_id = fields.Many2one(
        'no.purchase.reason',
        string="No purchase reason"
    )
    requires_reason = fields.Boolean(
        compute='_compute_requires_reason',
        store=True,
        string="Requires Reason"
    )
    parent_delivery_type = fields.Selection(
        related='route_id.delivery_type',
        store=True,
        readonly=True
    )
    parent_delivery_person = fields.Many2one(
        comodel_name='res.users',
        related='route_id.delivery_person_id',
        store=True,
        readonly=True,
    )
    allowed_client = fields.Many2many(
        comodel_name='res.partner',
        compute='_compute_allowed_client',
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10
    )

    possible_customer_withdrawal = fields.Boolean("Possible Withdrawal", tracking=True)
    reason_customer_withdrawal = fields.Many2one(
        'res.partner.category',
        domain=[('parent_id.name','=','Posible Baja')],
        string="Reason of Withdrawal", tracking=True
    )

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        if vals.get('reason_customer_withdrawal'):
            category = rec.reason_customer_withdrawal
            if category and category not in rec.client_id.category_id:
                rec.client_id.category_id = [(4, category.id)]
        return rec

    def write(self, vals):
        # save previous reason
        old_data = {
            rec.id: {
                'old_reason': rec.reason_customer_withdrawal.id if rec.reason_customer_withdrawal else None
            } for rec in self
        }

        res = super().write(vals)

        for rec in self:
            old_reason = old_data[rec.id]['old_reason']
            new_reason = rec.reason_customer_withdrawal
            partner = rec.client_id

            if vals.get('possible_customer_withdrawal') is False:
                rec.reason_customer_withdrawal = False
                if old_reason and old_reason in partner.category_id.ids:
                    partner.category_id = [(3, old_reason)]

            if vals.get('possible_customer_withdrawal') is True and new_reason:
                if new_reason.id not in partner.category_id.ids:
                    partner.category_id = [(4, new_reason.id)]

            if vals.get('reason_customer_withdrawal') and 'possible_customer_withdrawal' not in vals:
                if old_reason and old_reason in partner.category_id.ids:
                    partner.category_id = [(3, old_reason)]
                if new_reason and new_reason.id not in partner.category_id.ids:
                    partner.category_id = [(4, new_reason.id)]

        return res

    def unlink(self):
        for rec in self:
            reason = rec.reason_customer_withdrawal

            if reason and reason.id in rec.client_id.category_id.ids:
                rec.client_id.category_id = [(3, reason.id)]

            rec.route_message_post()
        return super().unlink()

    @api.onchange('possible_customer_withdrawal')
    def _onchange_possible_customer_withdrawal(self):
        if not self.possible_customer_withdrawal:
            self.reason_customer_withdrawal = False

    @api.depends('client_id.street', 'client_id.num', 'client_id.floor', 'client_id.apartment', 'client_id.city', 'client_id.state_id')
    def _compute_address_client_id(self):
        for record in self:
            if record.client_id:
                # Construimos la dirección de manera condicional
                address_parts = []
                if record.client_id.street:
                    address_part = record.client_id.street
                    if record.client_id.num:
                        address_part += " " + str(record.client_id.num)  # Concatenamos el número de la calle
                    address_parts.append(address_part)
                if record.client_id.floor:
                    address_parts.append("Piso " + str(record.client_id.floor))
                if record.client_id.apartment:
                    address_parts.append("Depto " + str(record.client_id.apartment))
                if record.client_id.city:
                    address_parts.append(record.client_id.city)
                if record.client_id.state_id:
                    address_parts.append(record.client_id.state_id.name)
                # Asignamos la dirección construida (se hace join de los componentes)
                record.client_address = ', '.join(address_parts) if address_parts else ''
            else:
                # Si no hay partner, dejamos el campo vacío
                record.client_address = ''

    @api.depends(
    'route_id',
    'template_route_id',
    'template_route_id.day',
    'parent_delivery_type',
    'parent_delivery_person',
    )
    def _compute_allowed_client(self):
        partner_obj = self.env['res.partner']
        for rec in self:
            rec.allowed_client = partner_obj.browse()
            if rec.route_id and rec.parent_delivery_type == 'common' and rec.parent_delivery_person:
                # users = self.env['res.users'].search([('partner_id', '=', rec.parent_delivery_person.id)])
                rec.allowed_client = partner_obj.search([('user_id', '=', rec.parent_delivery_person.id)], limit=None)

            elif rec.template_route_id:
                rec.allowed_client = partner_obj.search([('visit_day', '=', rec.template_route_id.day)], limit=None)

    @api.depends(
        'visit_status_id',
        'visit_status_id.requires_reason'
    )
    def _compute_requires_reason(self):
        for rec in self:
            if rec.visit_status_id:
                rec.requires_reason = rec.visit_status_id.requires_reason
            else:
                rec.requires_reason = False

    def _valid_field_parameter(self, field, name):
        return name == 'tracking' or super()._valid_field_parameter(field, name)

    def route_message_post(self):
        route = self.route_id
        if route:
            context_note = self.env.context.get('chatter_note', '')
            customer_name = self.client_id.name
            message = _("The customer %(customer)s was deleted ") % {'customer': customer_name}
            if context_note:
                message += context_note

            route.message_post(
                body=message,
            )
