import re
from datetime import datetime

from odoo import api, models

_ATTACHMENT_SPEC = {
    "company_vehicle": {"label": "Nuestro vehículo", "min": 1, "max": 1},
    "third_party_vehicle": {"label": "Vehículo del tercero", "min": 1, "max": 1},
    "third_party_policy": {"label": "Póliza del tercero", "min": 1, "max": 1},
    "third_party_license": {"label": "Registro del tercero", "min": 1, "max": 1},
    "third_party_vehicle_card": {"label": "Cédula del tercero", "min": 1, "max": 1},
    "driver_license": {"label": "Registro del conductor", "min": 1, "max": 2},
}
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class IvessAccidentIntake(models.Model):
    _name = "ivess.accident.intake"
    _inherit = "ivess.intake.mixin"
    _description = "Intake de tickets de siniestro desde middleware Ivess"

    _REQUIRED = (
        "business_unit",
        "patente",
        "dispatch",
        "driver_file_number",
        "driver_name",
        "driver_identification",
        "driver_address",
        "vehicle_damage",
        "facts_description",
        "third_party_name",
        "third_party_vehicle",
        "third_party_patente",
        "third_party_identification",
        "third_party_phone",
        "third_party_insurer",
        "third_party_vehicle_damage",
        "accident_date",
        "accident_time",
        "accident_address",
        "accident_city",
        "attachments",
    )
    _OPTIONAL = ("accident_notes", "partner_phone", "external_id")

    @api.model
    def create_ticket(self, **kwargs):
        if not kwargs:
            return self._intake_error_response("No se enviaron datos en el cuerpo de la solicitud")

        error = self._intake_check_params(kwargs, required=self._REQUIRED, optional=self._OPTIONAL)
        if error:
            return self._intake_error_response(error)

        attachments = kwargs.get("attachments") or []
        error = self._intake_validate_attachments(attachments, _ATTACHMENT_SPEC)
        if error:
            return self._intake_error_response(error)

        accident_date, date_error = self._parse_accident_date(kwargs["accident_date"])
        if date_error:
            return self._intake_error_response(date_error)

        accident_time, time_error = self._parse_accident_time(kwargs["accident_time"])
        if time_error:
            return self._intake_error_response(time_error)

        external_id = kwargs.get("external_id")
        existing = self._intake_find_existing_ticket(external_id)
        if existing:
            return self._intake_already_registered_response(existing)

        team = self._intake_get_team("workshop")
        if not team:
            return self._intake_error_response("No se encontró un equipo de tipo 'workshop'")

        patente = kwargs["patente"]
        equipment, patente_warning = self._intake_get_equipment(patente)
        dispatch_route = self._intake_resolve_dispatch(kwargs["dispatch"])
        third_party_plate = self._intake_normalize_patente(kwargs["third_party_patente"])

        vals = {
            "name": f"Siniestro - {patente} - {accident_date.strftime('%d/%m/%Y')}",
            "team_id": team.id,
            "ticket_source": "other",
            "partner_phone": kwargs.get("partner_phone", ""),
            "dispatch": kwargs["dispatch"],
            "dispatch_id": dispatch_route.id if dispatch_route else False,
            "equipment_id": equipment.id if equipment else False,
            "accident_business_unit": kwargs["business_unit"],
            "driver_file_number": kwargs["driver_file_number"],
            "driver_name": kwargs["driver_name"],
            "driver_identification": kwargs["driver_identification"],
            "driver_address": kwargs["driver_address"],
            "accident_vehicle_damage": kwargs["vehicle_damage"],
            "accident_facts": kwargs["facts_description"],
            "description": kwargs["facts_description"],
            "third_party_name": kwargs["third_party_name"],
            "third_party_vehicle": kwargs["third_party_vehicle"],
            "third_party_plate": third_party_plate,
            "third_party_identification": kwargs["third_party_identification"],
            "third_party_phone": kwargs["third_party_phone"],
            "third_party_insurer": kwargs["third_party_insurer"],
            "third_party_vehicle_damage": kwargs["third_party_vehicle_damage"],
            "accident_date": accident_date,
            "accident_time": accident_time,
            "accident_address": kwargs["accident_address"],
            "accident_city": kwargs["accident_city"],
            "accident_notes": kwargs.get("accident_notes", ""),
            "intake_payload": self._intake_format_payload(kwargs),
            "intake_external_id": external_id,
            "workshop_request_type": "accident",
        }

        maintenance_team = self._intake_get_workshop_maintenance_team()
        create_ctx = {"maintenance_team_id_ctx": maintenance_team.id} if maintenance_team else {}
        ticket = self.env["helpdesk.ticket"].with_context(**create_ctx).create(vals)
        self._intake_create_attachments(ticket, attachments, _ATTACHMENT_SPEC)

        warnings = [w for w in (patente_warning,) if w]
        return self._intake_success_response(ticket, warnings)

    def _parse_accident_date(self, value):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, fmt).date(), None
            except (TypeError, ValueError):
                continue
        return None, "El parámetro 'accident_date' debe tener formato AAAA-MM-DD o DD/MM/AAAA."

    def _parse_accident_time(self, value):
        match = _TIME_RE.match(value or "")
        if not match:
            return None, "El parámetro 'accident_time' debe tener formato HH:MM (00-23:00-59)."
        hours, minutes = int(match.group(1)), int(match.group(2))
        return hours + minutes / 60.0, None
