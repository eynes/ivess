from odoo.tests import tagged

from .common import IntakeTestCommon


@tagged("post_install", "-at_install")
class TestBreakdownIntake(IntakeTestCommon):
    def _base_payload(self, **overrides):
        payload = {
            "patente": self.plate,
            "dispatch": str(self.dispatch_number.number),
            "driver_name": "Juan Perez",
            "vehicle_model": "Ford Cargo",
            "vehicle_location": "Av. Mitre 1200, Avellaneda",
            "breakdown_reason": "Pinchadura",
        }
        payload.update(overrides)
        return payload

    def test_create_with_coordinates_sets_maps_link_and_urgent_priority(self):
        payload = self._base_payload(latitude="-34.6", longitude="-58.4")
        result = self.env["ivess.breakdown.intake"].create_ticket(**payload)
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertIn("maps.google.com/?q=-34.6,-58.4", ticket.maps_location)
        self.assertEqual(ticket.priority, "3")
        self.assertEqual(ticket.team_id.team_type, "workshop")
        self.assertEqual(ticket.workshop_request_type, "breakdown")

    def test_invalid_coordinates_keep_ticket_and_warn(self):
        payload = self._base_payload(
            latitude="not-a-number", longitude="-58.4", maps_location="texto libre"
        )
        result = self.env["ivess.breakdown.intake"].create_ticket(**payload)
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.maps_location, "texto libre")
        self.assertTrue(result["warnings"])

    def test_old_contract_aliases_still_work(self):
        result = self.env["ivess.breakdown.intake"].create_ticket(
            patente=self.plate,
            webhub_dispatch=str(self.dispatch_number.number),
            partner_id="Juan Perez",
            webhub_vehicle_model="Ford Cargo",
            webhub_description="Se quedó sin combustible",
            vehicle_location="Ruta 2 km 40",
            breakdown_reason="Sin combustible",
        )
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.driver_name, "Juan Perez")
        self.assertEqual(ticket.vehicle_model, "Ford Cargo")
        self.assertEqual(ticket.equipment_id, self.equipment)

    def test_missing_patente_returns_error(self):
        payload = self._base_payload()
        del payload["patente"]
        result = self.env["ivess.breakdown.intake"].create_ticket(**payload)
        self.assertIn("error", result)
        self.assertIn("patente", result["error"])
