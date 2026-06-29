from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)

WEEKDAY_MAPPING = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}

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
        string="Recorrido",
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
            ('sincronizado', 'Sincronizado'),
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
    delivery_number_override_id = fields.Many2one(
        'delivery.route.number',
        string='Reparto Override',
        copy=True,
    )
    delivery_number_id = fields.Many2one(
        'delivery.route.number',
        string="Reparto",
        compute='_compute_delivery_number_id',
        inverse='_inverse_delivery_number_id',
        store=True,
        tracking=True,
    )

    @api.depends('template_delivery_route_id.delivery_number_id', 'delivery_number_override_id')
    def _compute_delivery_number_id(self):
        for rec in self:
            rec.delivery_number_id = (
                rec.delivery_number_override_id
                or rec.template_delivery_route_id.delivery_number_id
            )

    def _inverse_delivery_number_id(self):
        for rec in self:
            rec.delivery_number_override_id = rec.delivery_number_id
    supervisor_id = fields.Many2one(
        'res.partner',
        string='Supervisor',
        related='delivery_number_id.supervisor_id',
        store=True,
        readonly=True,
    )
    supervisor_regional_id = fields.Many2one(
        'res.partner',
        string='Supervisor Regional',
        related='region_id.supervisor_id',
        store=True,
    )
    conductor_id = fields.Many2one(
        'res.partner',
        string='Conductor',
        related='delivery_number_id.conductor_id',
        store=True,
        readonly=True,
    )
    ayudante_id = fields.Many2one(
        'res.partner',
        string='Ayudante',
        related='delivery_number_id.ayudante_id',
        store=True,
        readonly=True,
    )
    region_id = fields.Many2one(
        'delivery.route.region',
        string='Regional',
        related='delivery_number_id.region_id',
        store=True,
        readonly=True,
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
        template = self.template_delivery_route_id
        if template:
            self.truck_id = template.truck_id
            self.delivery_route_line_ids = [(5, 0, 0)] + [
                (0, 0, {'client_id': line.client_id.id})
                for line in template.delivery_route_line_ids
            ]
        else:
            self.delivery_route_line_ids = [(5, 0, 0)]

    def _prepare_route_lines_from_template(self, template):
        """Prepara las líneas de la ruta copiándolas desde el template."""
        return [(0, 0, {
            'route_id': self.id,
            'client_id': line.client_id.id,
        }) for line in template.delivery_route_line_ids]

    @api.model_create_multi
    def create(self, vals_list):
        context = self.env.context
        for vals in vals_list:
            if vals.get('template_delivery_route_id') and not context.get('create_from_wizard'):
                template = self.env['template.delivery.route'].browse(vals['template_delivery_route_id'])
                if template:
                    # Asegúrate de que _prepare_route_lines_from_template devuelva
                    # el formato de comandos de Odoo: [(0, 0, {...}), (0, 0, {...})]
                    vals['delivery_route_line_ids'] = self._prepare_route_lines_from_template(template)
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            if 'template_delivery_route_id' in vals:
                if vals['template_delivery_route_id']:
                    template = self.env['template.delivery.route'].browse(vals['template_delivery_route_id'])
                    vals['delivery_route_line_ids'] = [(5, 0, 0)] + self._prepare_route_lines_from_template(template)
                else:
                    if 'truck_id' not in vals:
                        vals['truck_id'] = False
                    vals['delivery_route_line_ids'] = [(5, 0, 0)]  # Borra las líneas si se borra el template
        return super().write(vals)

    # def check_delivery_person(self):
    #     if self.delivery_person_id and self.truck_id:
    #         user = self.delivery_person_id
    #         return user not in self.truck_id.user_assigned_ids
    #     return False

    def action_set_synchronized(self):
        self.state = 'sincronizado'

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
            record.write({'state': 'closed'})
            created, updated = record._generate_next_week_route()
            record._post_next_routes_chatter(created, updated)

    def _post_next_routes_chatter(self, created, updated):
        lines = []
        for route in created.sorted('delivery_date'):
            lines.append(Markup('• %s (%s) — creada') % (route.name, route.delivery_date.strftime('%d/%m/%Y')))
        for route in updated.sorted('delivery_date'):
            lines.append(Markup('• %s (%s) — actualizada') % (route.name, route.delivery_date.strftime('%d/%m/%Y')))
        if lines:
            self.message_post(body=Markup('Rutas generadas al cerrar:<br/>') + Markup('<br/>').join(lines))

    def _generate_next_week_route(self):
        """Al cerrar la ruta, genera un único recorrido para la semana siguiente.
        Solo incluye clientes cuya próxima visita cae en esa fecha (frecuencia semanal).
        Clientes con otras frecuencias son gestionados por el cron mensual."""
        created = self.env['delivery.route']
        updated = self.env['delivery.route']

        if not self.template_delivery_route_id or not self.delivery_date:
            return created, updated

        template = self.template_delivery_route_id
        next_week_date = self.delivery_date + timedelta(days=7)

        client_ids = []
        for line in self.delivery_route_line_ids:
            client = line.client_id
            dist = client.distributions_ids.filtered(lambda d: d.distribution.id == template.id)
            if not dist:
                dist = client.distributions_ids
            frequency = dist[:1].frequency or client.frequency or 'weekly'
            if frequency == 'weekly':
                client_ids.append(client.id)

        if not client_ids:
            return created, updated

        existing_route = self.env['delivery.route'].search([
            ('delivery_date', '=', next_week_date),
            ('template_delivery_route_id', '=', template.id),
        ], limit=1)

        if existing_route:
            route = existing_route
            updated |= route
        else:
            route = self.env['delivery.route'].with_context(create_from_wizard=True).create({
                'name': "{} {}".format(template.name, next_week_date),
                'template_delivery_route_id': template.id,
                'delivery_date': next_week_date,
                'truck_id': self.truck_id.id,
                'delivery_number_id': template.delivery_number_id.id,
                'create_from_wizard': True,
            })
            created |= route

        existing_client_ids = route.delivery_route_line_ids.mapped('client_id').ids
        new_lines = [
            {'route_id': route.id, 'client_id': cid}
            for cid in client_ids
            if cid not in existing_client_ids
        ]
        if new_lines:
            self.env['delivery.route.line'].create(new_lines)

        return created, updated

    def _compute_next_visit_date(self, frequency, visit_day):
        """Retorna la próxima fecha de visita según la frecuencia y el día de visita del cliente."""
        current_date = self.delivery_date
        weekday_index = WEEKDAY_MAPPING.get(visit_day, current_date.weekday())

        if frequency == 'biweekly':
            base_date = current_date + timedelta(days=14)
        elif frequency == 'monthly':
            next_month_first = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            days_ahead = (weekday_index - next_month_first.weekday()) % 7
            return next_month_first + timedelta(days=days_ahead)
        else:  # weekly
            base_date = current_date + timedelta(days=7)

        # Ajustar al día de visita correcto a partir de base_date
        days_ahead = (weekday_index - base_date.weekday()) % 7
        return base_date + timedelta(days=days_ahead)

    def _validate_state(self):
        if self.state != 'in_progress':
            raise ValidationError(_("Solo se pueden cerrar registros en estado 'En Progreso'."))

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

    def action_create_bis(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'delivery.route.bis.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_route_id': self.id},
        }

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
        string='Ruta',
        # required=True,
        ondelete='cascade',
        copy=False,
    )
    template_route_id = fields.Many2one(
        'template.delivery.route',
        string='Recorrido',
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
    visit_hour_from = fields.Float(
        string='Hora de Visita Desde',
        related='client_id.visit_hour_from',
        store=True,
        readonly=True,
    )
    visit_hour_to = fields.Float(
        string='Hora de Visita Hasta',
        related='client_id.visit_hour_to',
        store=True,
        readonly=True,
    )
    effective_visit_hour = fields.Float(
        string='Hora Efectiva de Visita',
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='SO Relacionada',
    )
    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Remito Relacionado',
    )
    origin = fields.Char(
        string='Origen',
    )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)

        for rec, vals in zip(recs, vals_list):
            reason = vals.get('reason_customer_withdrawal')
            if reason and rec.client_id:
                category = self.env['res.partner.category'].browse(reason)
                if category not in rec.client_id.category_id:
                    rec.client_id.write({
                        'category_id': [(4, category.id)]
                    })
        return recs

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

        if not self.env.context.get('no_sync_distribution'):
            template_lines = self.filtered(lambda r: r.template_route_id and not r.route_id)
            distributions_to_unlink = self.env['partner.distribution']
            for rec in template_lines:
                distributions_to_unlink |= self.env['partner.distribution'].search([
                    ('distribution', '=', rec.template_route_id.id),
                    ('partner_id', '=', rec.client_id.id),
                ])
            res = super().unlink()
            distributions_to_unlink.with_context(no_sync_distribution=True).unlink()
            return res

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
    )
    def _compute_allowed_client(self):
        partner_obj = self.env['res.partner']
        for rec in self:
            rec.allowed_client = partner_obj.browse()
            if rec.template_route_id:
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
