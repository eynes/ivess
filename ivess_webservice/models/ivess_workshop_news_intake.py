from odoo import api, models

_ATTACHMENT_SPEC = {
    "image": {"label": "Imagen", "min": 0, "max": 2},
}


class IvessWorkshopNewsIntake(models.Model):
    _name = "ivess.workshop.news.intake"
    _inherit = "ivess.intake.mixin"
    _description = "Intake de novedades de taller desde middleware Ivess"

    _REQUIRED = ("dispatch", "patente", "observations")
    _OPTIONAL = ("attachments", "partner_phone", "external_id")

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

        external_id = kwargs.get("external_id")
        existing = self._intake_find_existing_ticket(external_id)
        if existing:
            return self._intake_already_registered_response(existing)

        team = self._intake_get_team("workshop")
        if not team:
            return self._intake_error_response("No se encontró un equipo de tipo 'workshop'")

        patente = kwargs["patente"]
        dispatch = kwargs["dispatch"]
        observations = kwargs["observations"]
        equipment, patente_warning = self._intake_get_equipment(patente)
        dispatch_route = self._intake_resolve_dispatch(dispatch)

        vals = {
            "name": f"Novedad - {patente} - {observations[:60]}",
            "team_id": team.id,
            "ticket_source": "other",
            "partner_phone": kwargs.get("partner_phone", ""),
            "dispatch": dispatch,
            "dispatch_id": dispatch_route.id if dispatch_route else False,
            "equipment_id": equipment.id if equipment else False,
            "description": observations,
            "intake_payload": self._intake_format_payload(kwargs),
            "intake_external_id": external_id,
            "workshop_request_type": "news",
        }

        maintenance_team = self._intake_get_workshop_maintenance_team()
        create_ctx = {"maintenance_team_id_ctx": maintenance_team.id} if maintenance_team else {}
        ticket = self.env["helpdesk.ticket"].with_context(**create_ctx).create(vals)
        self._intake_create_attachments(ticket, attachments, _ATTACHMENT_SPEC)

        warnings = [w for w in (patente_warning,) if w]
        return self._intake_success_response(ticket, warnings)
