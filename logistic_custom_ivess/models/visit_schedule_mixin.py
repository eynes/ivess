# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models

WEEKDAY_MAPPING = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}


class VisitScheduleMixin(models.AbstractModel):
    _name = 'visit.schedule.mixin'
    _description = 'Visit Schedule Mixin'

    def _compute_next_visit_date(self, base_date, frequency, visit_day):
        """Retorna la próxima fecha de visita a partir de base_date, según
        la frecuencia (weekly/biweekly/monthly) y el día de visita."""
        if not base_date:
            return False
        weekday_index = WEEKDAY_MAPPING.get(visit_day, base_date.weekday())

        if frequency == 'biweekly':
            interval_base = base_date + timedelta(days=14)
        elif frequency == 'monthly':
            next_month_first = (base_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            days_ahead = (weekday_index - next_month_first.weekday()) % 7
            return next_month_first + timedelta(days=days_ahead)
        else:  # weekly
            interval_base = base_date + timedelta(days=7)

        days_ahead = (weekday_index - interval_base.weekday()) % 7
        return interval_base + timedelta(days=days_ahead)
