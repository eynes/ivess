import html
import re

from odoo import models

ATTACHMENT_MAX_SIZE = 5 * 1024 * 1024  # 5 MB, por archivo, según el documento del chatbot
ATTACHMENT_ALLOWED_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
}
_PATENTE_STRIP_RE = re.compile(r"[\s\-.]")


class IvessIntakeMixin(models.AbstractModel):
    """Lógica común a los servicios de intake de tickets de taller/recargas.

    Centraliza lo que describe la tarea T16556 como "común" a los 4
    servicios del chatbot de WhatsApp: validación de parámetros, patente,
    reparto, idempotencia por external_id, adjuntos y payload de ingreso.
    """

    _name = "ivess.intake.mixin"
    _description = "Mixin de intake de tickets Ivess"

    # -- 4.1 Parámetros ----------------------------------------------------
    def _intake_check_params(self, kwargs, required=(), optional=()):
        allowed = set(required) | set(optional)
        unknown = set(kwargs) - allowed
        if unknown:
            return (
                "Parámetros no reconocidos: %s. Los parámetros aceptados son: %s."
                % (", ".join(sorted(unknown)), ", ".join(sorted(allowed)))
            )
        missing = [name for name in required if not kwargs.get(name)]
        if missing:
            return "Faltan los siguientes parámetros requeridos: %s." % ", ".join(missing)
        return None

    # -- 4.2 Patente ---------------------------------------------------------
    def _intake_normalize_patente(self, patente):
        return _PATENTE_STRIP_RE.sub("", patente or "").upper()

    def _intake_get_equipment(self, patente):
        """Devuelve (equipment, warning). Nunca descarta el reporte por patente desconocida."""
        normalized = self._intake_normalize_patente(patente)
        if not normalized:
            return self.env["maintenance.equipment"], None
        equipment = self.env["maintenance.equipment"].with_context(lang="es_AR").search(
            [("name", "=", normalized)], limit=1
        )
        if equipment:
            return equipment, None
        warning = (
            "Patente '%s' no reconocida: el ticket se creo sin equipo y queda "
            "para revision del taller." % patente
        )
        return self.env["maintenance.equipment"], warning

    # -- 4.3 Reparto -----------------------------------------------------
    def _intake_resolve_dispatch(self, dispatch):
        if not dispatch:
            return self.env["delivery.route.number"]
        try:
            number = int(dispatch)
        except (TypeError, ValueError):
            return self.env["delivery.route.number"]
        return self.env["delivery.route.number"].search([("number", "=", number)], limit=1)

    # -- 4.4 Idempotencia --------------------------------------------------
    def _intake_find_existing_ticket(self, external_id):
        if not external_id:
            return self.env["helpdesk.ticket"]
        return self.env["helpdesk.ticket"].search(
            [("intake_external_id", "=", external_id)], limit=1
        )

    def _intake_already_registered_response(self, ticket):
        return {
            "success": True,
            "ticket_id": ticket.id,
            "ticket_name": ticket.name,
            "already_registered": True,
            "warnings": [],
        }

    # -- Equipo helpdesk ---------------------------------------------------
    def _intake_get_team(self, team_type):
        return self.env["helpdesk.team"].search([("team_type", "=", team_type)], limit=1)

    def _intake_get_workshop_maintenance_team(self):
        return self.env["maintenance.team"].search([("is_workshop", "=", True)], limit=1)

    # -- 4.6 Payload de ingreso ---------------------------------------------
    def _intake_format_payload(self, data):
        """Arma el HTML de intake_payload sin base64 y con el contenido escapado.

        El campo es Html sin sanitizar (sanitize=False) y lo completa texto
        libre escrito por el chofer en WhatsApp, así que hay que escapar acá.
        """
        sanitized = dict(data)
        if sanitized.get("attachments"):
            sanitized["attachments"] = [
                {"field": a.get("field"), "filename": a.get("filename")}
                for a in sanitized["attachments"]
            ]
        lines = "\n".join(f"{k}: {v}" for k, v in sanitized.items())
        escaped = html.escape(lines)
        return (
            "<pre style='font-size:12px;white-space:pre;overflow-x:auto;"
            f"margin:0;font-family:monospace'>{escaped}</pre>"
        )

    # -- 4.5 Adjuntos --------------------------------------------------------
    def _intake_validate_attachments(self, attachments, attachment_spec):
        """Valida `attachments` contra `attachment_spec` sin crear nada todavía.

        attachment_spec: {field: {"label": str, "min": int, "max": int}}
        Devuelve un mensaje de error (str) o None si todo es válido.
        """
        attachments = attachments or []
        allowed_fields = set(attachment_spec)
        unknown_fields = {a.get("field") for a in attachments} - allowed_fields
        if unknown_fields:
            return (
                "Campo de adjunto no reconocido: %s. Los campos aceptados son: %s."
                % (", ".join(sorted(unknown_fields)), ", ".join(sorted(allowed_fields)))
            )

        counts = {}
        for attachment in attachments:
            field = attachment.get("field")
            counts[field] = counts.get(field, 0) + 1
            mimetype = attachment.get("mimetype")
            if mimetype not in ATTACHMENT_ALLOWED_MIMETYPES:
                return (
                    "Tipo de archivo no soportado '%s' en el campo '%s'. Tipos aceptados: %s."
                    % (mimetype, field, ", ".join(sorted(ATTACHMENT_ALLOWED_MIMETYPES)))
                )
            data = attachment.get("data") or ""
            # base64 decodificado ~= 3/4 del tamaño del string codificado
            estimated_size = len(data) * 3 / 4
            if estimated_size > ATTACHMENT_MAX_SIZE:
                return (
                    "El adjunto '%s' supera el máximo de 5 MB."
                    % attachment.get("filename", field)
                )

        for field, spec in attachment_spec.items():
            count = counts.get(field, 0)
            if count < spec.get("min", 0):
                return "Falta el adjunto requerido '%s'." % spec.get("label", field)
            if spec.get("max") is not None and count > spec["max"]:
                return "Se recibieron demasiados adjuntos para '%s'." % spec.get("label", field)
        return None

    def _intake_create_attachments(self, ticket, attachments, attachment_spec):
        attachments = attachments or []
        counters = {}
        created = self.env["ir.attachment"]
        for attachment in attachments:
            field = attachment.get("field")
            label = attachment_spec.get(field, {}).get("label", field)
            counters[field] = counters.get(field, 0) + 1
            name = f"{label} {counters[field]} - {attachment.get('filename')}"
            created |= self.env["ir.attachment"].create({
                "name": name,
                "datas": attachment.get("data"),
                "mimetype": attachment.get("mimetype"),
                "res_model": "helpdesk.ticket",
                "res_id": ticket.id,
            })
        if created:
            ticket.message_post(
                body="Adjuntos recibidos: %s" % ", ".join(created.mapped("name")),
                attachment_ids=created.ids,
            )
        return created

    # -- Respuesta estándar --------------------------------------------------
    def _intake_success_response(self, ticket, warnings=None):
        return {
            "success": True,
            "ticket_id": ticket.id,
            "ticket_name": ticket.name,
            "already_registered": False,
            "warnings": warnings or [],
        }

    def _intake_error_response(self, message):
        return {"error": message}
