from odoo import api, models


class IvessHelpdeskIntake(models.Model):
    _name = "ivess.helpdesk.intake"
    _description = "Intake de tickets de helpdesk desde middleware Ivess"

    @api.model
    def create_ticket(self, **kwargs):
        patente = kwargs.get("patente", "")
        items = kwargs.get("items") or []
        intake_user = kwargs.get("user", "")

        team = self._get_workshop_team()
        if not team:
            return {"error": "No se encontró un equipo de tipo 'workshop'"}

        equipment = self._get_equipment(patente)
        if not equipment:
            return {"error": f"Equipo '{patente}' no encontrado"}

        payload = self._format_payload(kwargs)
        ticket = self._create_helpdesk_ticket(team, equipment, patente, items, intake_user, payload)
        return {"ticket_id": ticket.id, "ticket_name": ticket.name}

    def _get_workshop_team(self):
        return self.env["helpdesk.team"].search(
            [("team_type", "=", "workshop")],
            limit=1,
        )

    def _get_equipment(self, patente):
        return self.env["maintenance.equipment"].with_context(lang="es_AR").search(
            [("name", "=", patente)],
            limit=1,
        )

    def _format_payload(self, data):
        lines = "\n".join(f"{k}: {v}" for k, v in data.items())
        return f"<pre style='font-size:12px;white-space:pre;overflow-x:auto;margin:0;font-family:monospace'>{lines}</pre>"

    def _build_item_lines(self, items):
        return [
            (0, 0, {"name": k, "value": str(v)})
            for item in items
            for k, v in item.items()
        ]

    def _create_helpdesk_ticket(self, team, equipment, patente, items, intake_user="", payload=None):
        sequence = self.env["ir.sequence"].next_by_code("ivess.helpdesk.intake.cs")
        return self.env["helpdesk.ticket"].create({
            "name": sequence,
            "user_id": self.env.user.id,
            "equipment_id": equipment.id,
            "ticket_source": "other",
            "team_id": team.id,
            "item_ids": self._build_item_lines(items),
            "intake_user": intake_user,
            "intake_payload": payload,
        })
