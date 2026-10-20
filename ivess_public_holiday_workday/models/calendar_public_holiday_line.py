from odoo import fields, models


class CalendarPublicHolidayLine(models.Model):
    _inherit = "calendar.public.holiday.line"

    is_workday = fields.Boolean(
        string="Laborable",
        help="Si está marcado, el día figura como feriado en el calendario pero "
        "se trabaja igual: no se descuenta como día no laborable.",
    )

    def _prepare_holidays_meeting_values(self):
        values = super()._prepare_holidays_meeting_values()
        if self.is_workday:
            values["show_as"] = "free"
            values["name"] = self.env._("%s (Laborable)", values["name"])
            categ = self.env.ref(
                "ivess_public_holiday_workday.event_type_holiday_workday", False
            )
            if categ:
                values["categ_ids"] = [(6, 0, categ.ids)]
        return values

    def write(self, vals):
        res = super().write(vals)
        if "is_workday" in vals:
            for line in self.filtered("meeting_id"):
                line.meeting_id.write(line._prepare_holidays_meeting_values())
        return res


class CalendarPublicHoliday(models.Model):
    _inherit = "calendar.public.holiday"

    def _get_domain_states_filter(self, pholidays, start_dt, end_dt, partner_id=None):
        domain = super()._get_domain_states_filter(
            pholidays, start_dt, end_dt, partner_id=partner_id
        )
        domain.append(("is_workday", "=", False))
        return domain
