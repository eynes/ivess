# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from dateutil.rrule import rrule, WEEKLY
from datetime import datetime, timedelta
from collections import defaultdict


WEEKDAY_MAPPING = {
    'monday': 0,
    'tuesday': 1, 
    'wednesday': 2, 
    'thursday': 3,
    'friday': 4, 
    'saturday': 5, 
    'sunday': 6
}

FREQUENCY_MAPPING = {
    'weekly': 1,
    'biweekly': 2,
    'monthly': 4, 
}

class DeliveryRouteMassCreateWizard(models.TransientModel):
    _name = 'delivery.route.mass.create.wizard'
    _description = 'Wizard to mass create delivery routes'

    date_from = fields.Date(string="Date from", required=True)
    date_to = fields.Date(string="Date to", required=True)
    template_delivery_route_id = fields.Many2one('template.delivery.route', string="Template route", required=True)

    def _validate_dates(self):
        """Valida que la fecha de inicio (date_from) no sea mayor que la fecha de fin (date_to).
            Si la fecha de inicio es posterior a la fecha de fin, lanza un error de validación.
        """
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("The Start Date must be less than or equal to the End Date."))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Verifica que las fechas sean válidas cuando se guarde el registro."""
        self._validate_dates()

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        self._validate_dates()

    def route_exists(self, date, template_delivery_route_id):
        return self.env['delivery.route'].search_count([
            ('delivery_date', '=', date), 
            ('template_delivery_route_id', '=', template_delivery_route_id)
        ])

    def prepare_vals_delivery_route(self, date):
        """Prepara los valores necesarios para crear una nueva ruta de entrega.
        Args:
            date (date): Fecha de la entrega.
        Returns:
            dict: Diccionario con los valores para la creación de la ruta.
        """
        return {
            'name': "{} {}".format(self.template_delivery_route_id.name, date),
            'template_delivery_route_id': self.template_delivery_route_id.id,
            'delivery_date': date,
            'truck_id': self.template_delivery_route_id.truck_id.id,
            'delivery_number_id': self.template_delivery_route_id.delivery_number_id.id,
            # 'allow_price_editing': self.template_delivery_route_id.allow_price_editing,
            # 'allow_reordering': self.template_delivery_route_id.allow_reordering,
            'create_from_wizard': True,
        }

    def get_dates(self, assigned_weekday_index):
        """Genera una lista de fechas dentro del rango seleccionado, filtrando por el día de la semana asignado.
        Args:
            assigned_weekday_index (int): Índice del día de la semana (0=Lunes, 6=Domingo).
        Returns:
            list[datetime]: Lista de fechas en las que ocurren las entregas.
        """
        return list(
            rrule(
                WEEKLY, 
                dtstart=self.date_from, 
                until=self.date_to, 
                byweekday=assigned_weekday_index
            )
        )

    def action_generate_routes(self):
        """Genera rutas de reparto en función del período seleccionado y el día de la semana asignado.
        - Verifica si hay clientes asignados al modelo de ruta de entrega.
        - Obtiene todas las fechas dentro del rango que coincidan con el día de la semana especificado.
        - Crea las rutas de entrega.
        - Asigna los clientes a visitar en las rutas generadas.
        Returns:
            dict: Acción para abrir la vista de las rutas generadas.
        """
        self.ensure_one()
        template_route = self.template_delivery_route_id
        assigned_weekday = template_route.day 
        customers_to_visit = template_route.delivery_route_line_ids
        
        if not customers_to_visit:
            raise ValidationError(_("No customers to visit in the selected Delivery Assignment."))

        assigned_weekday_index = WEEKDAY_MAPPING.get(assigned_weekday)
        if assigned_weekday_index is None:
            raise ValidationError(_("Invalid day of the week in the Delivery Assignment."))

        # Genera todas las fechas en el rango que coincidan con el día de la semana
        dates = self.get_dates(assigned_weekday_index)
        created_routes = self.env['delivery.route']
        for current_date in dates:
            data = self.prepare_vals_delivery_route(date=current_date.date())  # Convertimos a `date`
            route_exists = self.route_exists(current_date, data.get('template_delivery_route_id'))
            if route_exists > 0:
                continue
            delivery_route = self.env['delivery.route'].with_context({'create_from_wizard': True}).create(data)
            created_routes |= delivery_route
        
        self.set_client_to_visit(created_routes)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Delivery Routes'),
            'res_model': 'delivery.route',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_routes.ids)],
            'target': 'current',
        }

    def set_client_to_visit(self, created_routes):
        """Asigna los clientes a las rutas generadas según la frecuencia de visita.
        - Si la frecuencia del cliente es mensual, se asigna solo a la primera fecha del mes disponible.
        - Si la frecuencia es semanal o quincenal, se asignan fechas de acuerdo con el intervalo definido.
        Args:
            created_routes (recordset): Conjunto de rutas de entrega creadas.
        """
        self.ensure_one()
        route_dates = sorted(route.delivery_date for route in created_routes)
        
        # Agrupar por mes para clientes mensuales
        monthly_dates = defaultdict(list)
        for date in route_dates:
            monthly_dates[date.strftime("%Y-%m")].append(date)

        for line in self.template_delivery_route_id.delivery_route_line_ids:
            client = line.client_id
            interval = FREQUENCY_MAPPING.get(client.frequency, 1)

            if client.frequency == 'monthly':
                # Tomar la primera fecha de cada mes
                selected_dates = [dates[0] for dates in monthly_dates.values()]
            else:
                # Para semanal y quincenal
                selected_dates = route_dates[::interval]

            selected_routes = created_routes.filtered(lambda r: r.delivery_date in selected_dates)

            self.env['delivery.route.line'].create([
                {'route_id': route.id, 'client_id': client.id}
                for route in selected_routes
            ])