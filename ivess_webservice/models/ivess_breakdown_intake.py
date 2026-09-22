from odoo import api, models


class IvessBreakdownIntake(models.Model):
    _name = "ivess.breakdown.intake"
    _inherit = "ivess.intake.mixin"
    _description = "Intake de tickets de auxilio desde middleware Ivess"

    # Alias -> nombre nuevo, para no romper a quien ya integró con el
    # contrato viejo (solo hay 3 tickets de prueba de julio, pero igual).
    _ALIASES = {
        "webhub_dispatch": "dispatch",
        "webhub_vehicle_model": "vehicle_model",
        "webhub_description": "description",
        "partner_id": "driver_name",
    }
    _REQUIRED = (
        "patente",
        "dispatch",
        "driver_name",
        "vehicle_model",
        "vehicle_location",
        "breakdown_reason",
    )
    _OPTIONAL = ("description", "latitude", "longitude", "maps_location", "partner_phone", "external_id")

    @api.model
    def create_ticket(self, **kwargs):
        if not kwargs:
            return self._intake_error_response("No se enviaron datos en el cuerpo de la solicitud")

        allowed = set(self._REQUIRED) | set(self._OPTIONAL) | set(self._ALIASES)
        unknown = set(kwargs) - allowed
        if unknown:
            return self._intake_error_response(
                "Parámetros no reconocidos: %s. Los parámetros aceptados son: %s."
                % (", ".join(sorted(unknown)), ", ".join(sorted(allowed)))
            )

        values = self._resolve_aliases(kwargs)
        missing = [name for name in self._REQUIRED if not values.get(name)]
        if missing:
            return self._intake_error_response(
                "Faltan los siguientes parámetros requeridos: %s." % ", ".join(missing)
            )

        external_id = kwargs.get("external_id")
        existing = self._intake_find_existing_ticket(external_id)
        if existing:
            return self._intake_already_registered_response(existing)

        team = self._intake_get_team("workshop")
        if not team:
            return self._intake_error_response("No se encontró un equipo de tipo 'workshop'")

        equipment, patente_warning = self._intake_get_equipment(values["patente"])
        maps_location, latlong_warning = self._resolve_maps_location(kwargs)
        dispatch_route = self._intake_resolve_dispatch(values["dispatch"])

        vals = {
            "name": f"Auxilio - {values['breakdown_reason']} - {values['patente']}",
            "team_id": team.id,
            "ticket_source": "other",
            "partner_phone": kwargs.get("partner_phone", ""),
            "dispatch": values["dispatch"],
            "webhub_dispatch": values["dispatch"],
            "dispatch_id": dispatch_route.id if dispatch_route else False,
            "driver_name": values["driver_name"],
            "vehicle_model": values["vehicle_model"],
            "webhub_vehicle_model": values["vehicle_model"],
            "description": values.get("description", ""),
            "vehicle_location": values["vehicle_location"],
            "breakdown_reason": values["breakdown_reason"],
            "maps_location": maps_location,
            "equipment_id": equipment.id if equipment else False,
            "intake_payload": self._intake_format_payload(kwargs),
            "intake_external_id": external_id,
            "workshop_request_type": "breakdown",
            "priority": "3",
        }

        maintenance_team = self._intake_get_workshop_maintenance_team()
        create_ctx = {"maintenance_team_id_ctx": maintenance_team.id} if maintenance_team else {}
        ticket = self.env["helpdesk.ticket"].with_context(**create_ctx).create(vals)

        warnings = [w for w in (patente_warning, latlong_warning) if w]
        return self._intake_success_response(ticket, warnings)

    def _resolve_aliases(self, kwargs):
        values = dict(kwargs)
        for old_name, new_name in self._ALIASES.items():
            if kwargs.get(old_name) and not kwargs.get(new_name):
                values[new_name] = kwargs[old_name]
        return values

    def _resolve_maps_location(self, kwargs):
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        if latitude is None or longitude is None:
            return kwargs.get("maps_location", ""), None
        try:
            lat, lng = float(latitude), float(longitude)
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
        except (TypeError, ValueError):
            return kwargs.get("maps_location", ""), (
                "Coordenadas inválidas: se usó la ubicación de texto tal cual fue recibida."
            )
        return f"https://maps.google.com/?q={lat},{lng}", None
