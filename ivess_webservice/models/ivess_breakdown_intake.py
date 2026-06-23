from odoo import api, models


class IvessBreakdownIntake(models.Model):
    _name = "ivess.breakdown.intake"
    _description = "Intake de tickets de auxilio desde middleware Ivess"

    @api.model
    def create_ticket(self, **kwargs):
        if not kwargs:
            return {"error": "No se enviaron datos en el cuerpo de la solicitud"}

        partner_name = kwargs.get("partner_id", "")
        partner_phone = kwargs.get("partner_phone", "")
        webhub_dispatch = kwargs.get("webhub_dispatch", "")
        webhub_vehicle_model = kwargs.get("webhub_vehicle_model", "")
        webhub_description = kwargs.get("webhub_description", "")
        vehicle_location = kwargs.get("vehicle_location", "")
        maps_location = kwargs.get("maps_location", "")
        breakdown_reason = kwargs.get("breakdown_reason", "")

        team = self._get_workshop_team()
        if not team:
            return {"error": "No se encontró un equipo de tipo 'workshop'"}

        partner = self._get_partner(partner_name) if partner_name else None
        equipment = self._get_equipment(webhub_vehicle_model) if webhub_vehicle_model else None

        ticket = self._create_helpdesk_ticket(
            team=team,
            partner=partner,
            equipment=equipment,
            partner_phone=partner_phone,
            webhub_dispatch=webhub_dispatch,
            webhub_vehicle_model=webhub_vehicle_model,
            webhub_description=webhub_description,
            vehicle_location=vehicle_location,
            maps_location=maps_location,
            breakdown_reason=breakdown_reason,
            payload=self._format_payload(kwargs),
        )
        return {"ticket_id": ticket.id, "ticket_name": ticket.name}

    def _format_payload(self, data):
        lines = "\n".join(f"{k}: {v}" for k, v in data.items())
        return f"<pre style='font-size:12px;white-space:pre;overflow-x:auto;margin:0;font-family:monospace'>{lines}</pre>"

    def _get_workshop_team(self):
        return self.env["helpdesk.team"].search(
            [("team_type", "=", "workshop")],
            limit=1,
        )

    def _get_partner(self, name):
        return self.env["res.partner"].search(
            [("name", "ilike", name)],
            limit=1,
        )

    def _get_equipment(self, name):
        return self.env["maintenance.equipment"].with_context(lang="es_AR").search(
            [("name", "=", name)],
            limit=1,
        )

    def _create_helpdesk_ticket(self, team, partner, equipment, partner_phone, webhub_dispatch,
                                webhub_vehicle_model, webhub_description, vehicle_location, maps_location,
                                breakdown_reason, payload=None):
        vals = {
            "name": f"Auxilio - {breakdown_reason}" if breakdown_reason else "Auxilio",
            "team_id": team.id,
            "ticket_source": "other",
            "partner_phone": partner_phone,
            "webhub_dispatch": webhub_dispatch,
            "webhub_vehicle_model": webhub_vehicle_model,
            "vehicle_model": webhub_vehicle_model,
            "webhub_description": webhub_description,
            "vehicle_location": vehicle_location,
            "maps_location": maps_location,
            "breakdown_reason": breakdown_reason,
            "intake_payload": payload,
        }
        if partner:
            vals["partner_id"] = partner.id
        if equipment:
            vals["equipment_id"] = equipment.id
        return self.env["helpdesk.ticket"].create(vals)
