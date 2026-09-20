from odoo import api, models

_REQUEST_MAX_LENGTH = 600


class IvessRefillIntake(models.Model):
    _name = "ivess.refill.intake"
    _inherit = "ivess.intake.mixin"
    _description = "Intake de tickets de recarga desde middleware Ivess"

    _REQUIRED = ("refill_type", "dispatch", "request")
    _OPTIONAL = ("vehicle_location", "to_dispatch", "partner_phone", "external_id")

    @api.model
    def create_ticket(self, **kwargs):
        if not kwargs:
            return self._intake_error_response("No se enviaron datos en el cuerpo de la solicitud")

        error = self._intake_check_params(kwargs, required=self._REQUIRED, optional=self._OPTIONAL)
        if error:
            return self._intake_error_response(error)

        refill_type = kwargs["refill_type"]
        if refill_type not in ("factory", "street"):
            return self._intake_error_response(
                "El parámetro 'refill_type' debe ser 'factory' o 'street'."
            )

        error = self._validate_refill_type_params(refill_type, kwargs)
        if error:
            return self._intake_error_response(error)

        request = kwargs["request"]
        if len(request) > _REQUEST_MAX_LENGTH:
            return self._intake_error_response(
                "El parámetro 'request' supera el máximo de %s caracteres." % _REQUEST_MAX_LENGTH
            )

        external_id = kwargs.get("external_id")
        existing = self._intake_find_existing_ticket(external_id)
        if existing:
            return self._intake_already_registered_response(existing)

        team = self._intake_get_team("refill")
        if not team:
            return self._intake_error_response(
                "No se encontró un equipo de tipo 'refill'. Debe crearse el equipo 'Recargas'."
            )

        dispatch = kwargs["dispatch"]
        dispatch_route = self._intake_resolve_dispatch(dispatch)
        to_dispatch = kwargs.get("to_dispatch", "")
        to_dispatch_route = self._intake_resolve_dispatch(to_dispatch) if to_dispatch else False

        vals = {
            "name": self._build_ticket_name(refill_type, dispatch, to_dispatch),
            "team_id": team.id,
            "ticket_source": "other",
            "partner_phone": kwargs.get("partner_phone", ""),
            "refill_type": refill_type,
            "dispatch": dispatch,
            "dispatch_id": dispatch_route.id if dispatch_route else False,
            "vehicle_location": kwargs.get("vehicle_location", ""),
            "refill_to_dispatch": to_dispatch,
            "refill_to_dispatch_id": to_dispatch_route.id if to_dispatch_route else False,
            "description": request,
            "intake_payload": self._intake_format_payload(kwargs),
            "intake_external_id": external_id,
        }
        ticket = self.env["helpdesk.ticket"].create(vals)
        return self._intake_success_response(ticket)

    def _validate_refill_type_params(self, refill_type, kwargs):
        if refill_type == "factory":
            if kwargs.get("to_dispatch"):
                return "El parámetro 'to_dispatch' no aplica para refill_type 'factory'."
            missing = [
                name for name in ("dispatch", "vehicle_location", "request") if not kwargs.get(name)
            ]
            if missing:
                return "Faltan los siguientes parámetros requeridos: %s." % ", ".join(missing)
            return None

        # street
        missing = [name for name in ("dispatch", "to_dispatch", "request") if not kwargs.get(name)]
        if missing:
            return "Faltan los siguientes parámetros requeridos: %s." % ", ".join(missing)
        if kwargs["dispatch"] == kwargs["to_dispatch"]:
            return "El reparto de origen y el de destino no pueden ser el mismo."
        return None

    def _build_ticket_name(self, refill_type, dispatch, to_dispatch):
        if refill_type == "factory":
            return f"Recarga fabrica - Reparto {dispatch}"
        return f"Recarga en calle - Reparto {dispatch} -> {to_dispatch}"
