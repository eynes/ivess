from odoo.tests import tagged

from .common import IntakeTestCommon


@tagged("post_install", "-at_install")
class TestAccidentIntake(IntakeTestCommon):
    def _base_payload(self, **overrides):
        payload = {
            "business_unit": "El Jumillano",
            "patente": self.plate,
            "dispatch": str(self.dispatch_number.number),
            "driver_file_number": "1234",
            "driver_name": "Juan Perez",
            "driver_identification": "30111222",
            "driver_address": "Calle Falsa 123",
            "vehicle_damage": "Golpe en el paragolpe",
            "facts_description": "Colisión en la esquina",
            "third_party_name": "Maria Lopez",
            "third_party_vehicle": "Fiat Cronos",
            "third_party_patente": "ab 648-ug",
            "third_party_identification": "28999111",
            "third_party_phone": "1155554444",
            "third_party_insurer": "La Caja",
            "third_party_vehicle_damage": "Puerta abollada",
            "accident_date": "15/09/2026",
            "accident_time": "13:30",
            "accident_address": "Av. Siempre Viva 742",
            "accident_city": "Avellaneda",
            "attachments": self._full_attachments(),
        }
        payload.update(overrides)
        return payload

    def _full_attachments(self):
        return [
            self._make_attachment("company_vehicle", filename="a.jpg"),
            self._make_attachment("third_party_vehicle", filename="b.jpg"),
            self._make_attachment("third_party_policy", filename="c.pdf", mimetype="application/pdf"),
            self._make_attachment("third_party_license", filename="d.jpg"),
            self._make_attachment("third_party_vehicle_card", filename="e.jpg"),
            self._make_attachment("driver_license", filename="f_frente.jpg"),
            self._make_attachment("driver_license", filename="f_dorso.jpg"),
        ]

    def test_full_submission_creates_ticket_with_all_fields(self):
        result = self.env["ivess.accident.intake"].create_ticket(**self._base_payload())
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.workshop_request_type, "accident")
        self.assertEqual(ticket.equipment_id, self.equipment)
        self.assertEqual(ticket.third_party_plate, "AB648UG")
        self.assertEqual(str(ticket.accident_date), "2026-09-15")
        self.assertAlmostEqual(ticket.accident_time, 13.5)
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", ticket.id)]
        )
        self.assertEqual(len(attachments), 7)

    def test_missing_policy_attachment_creates_nothing(self):
        before = self.env["helpdesk.ticket"].search_count([])
        attachments = [a for a in self._full_attachments() if a["field"] != "third_party_policy"]
        result = self.env["ivess.accident.intake"].create_ticket(
            **self._base_payload(attachments=attachments)
        )
        self.assertIn("error", result)
        self.assertEqual(self.env["helpdesk.ticket"].search_count([]), before)

    def test_both_accepted_date_formats_are_valid(self):
        result_slash = self.env["ivess.accident.intake"].create_ticket(
            **self._base_payload(accident_date="15/09/2026")
        )
        result_iso = self.env["ivess.accident.intake"].create_ticket(
            **self._base_payload(accident_date="2026-09-15")
        )
        self.assertTrue(result_slash.get("success"))
        self.assertTrue(result_iso.get("success"))

    def test_invalid_date_format_returns_error(self):
        result = self.env["ivess.accident.intake"].create_ticket(
            **self._base_payload(accident_date="ayer")
        )
        self.assertIn("error", result)

    def test_invalid_time_format_returns_error(self):
        result = self.env["ivess.accident.intake"].create_ticket(
            **self._base_payload(accident_time="25:99")
        )
        self.assertIn("error", result)
