from odoo import api, models


class IvessHelpdeskIntake(models.Model):
    _name = "ivess.helpdesk.intake"
    _description = "Intake de tickets de helpdesk desde middleware Ivess"

    @api.model
    def create_ticket(self, **kwargs):
        user_key = kwargs.get("user", "")
        patente = kwargs.get("patente", "")
        items = kwargs.get("items") or []

        user = self._get_user(user_key)
        if not user:
            return {"error": f"Usuario '{user_key}' no encontrado"}

        team = self._get_workshop_team()
        if not team:
            return {"error": "No se encontró un equipo de tipo 'workshop'"}

        equipment = self._get_equipment(patente)
        if not equipment:
            return {"error": f"Equipo '{patente}' no encontrado"}

        ticket = self._create_helpdesk_ticket(user, team, equipment, patente, items)
        return {"ticket_id": ticket.id, "ticket_name": ticket.name}

    def _get_user(self, user):
        return self.env["res.users"].search(
            ["|", ("login", "=", user), ("name", "ilike", user)],
            limit=1,
        )

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

    def _build_item_lines(self, items):
        return [
            (0, 0, {"name": k, "value": str(v)})
            for item in items
            for k, v in item.items()
        ]

    def _create_helpdesk_ticket(self, user, team, equipment, patente, items):
        return self.env["helpdesk.ticket"].create({
            "name": f"Taller - {patente}" if patente else "Taller",
            "user_id": user.id,
            "equipment_id": equipment.id,
            "ticket_source": "other",
            "team_id": team.id,
            "item_ids": self._build_item_lines(items),
        })
