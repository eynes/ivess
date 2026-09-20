from odoo.tests import tagged

from .common import IntakeTestCommon


@tagged("post_install", "-at_install")
class TestWorkshopNewsIntake(IntakeTestCommon):
    def _base_payload(self, **overrides):
        payload = {
            "dispatch": str(self.dispatch_number.number),
            "patente": self.plate,
            "observations": "Ruido en el tren delantero al frenar",
        }
        payload.update(overrides)
        return payload

    def test_create_with_two_photos(self):
        payload = self._base_payload(
            attachments=[
                self._make_attachment("image", filename="a.jpg"),
                self._make_attachment("image", filename="b.jpg"),
            ]
        )
        result = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.workshop_request_type, "news")
        self.assertEqual(ticket.equipment_id, self.equipment)
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", ticket.id)]
        )
        self.assertEqual(len(attachments), 2)

    def test_create_without_photos(self):
        result = self.env["ivess.workshop.news.intake"].create_ticket(**self._base_payload())
        self.assertTrue(result.get("success"))

    def test_three_photos_is_rejected_and_creates_nothing(self):
        before = self.env["helpdesk.ticket"].search_count([])
        payload = self._base_payload(
            attachments=[
                self._make_attachment("image", filename="a.jpg"),
                self._make_attachment("image", filename="b.jpg"),
                self._make_attachment("image", filename="c.jpg"),
            ]
        )
        result = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        self.assertIn("error", result)
        self.assertEqual(self.env["helpdesk.ticket"].search_count([]), before)

    def test_oversized_photo_is_rejected(self):
        # base64 infla ~4/3: 8 MB de texto codificado ~= 6 MB decodificados
        oversized_data = "A" * (8 * 1024 * 1024)
        payload = self._base_payload(
            attachments=[self._make_attachment("image", data=oversized_data)]
        )
        result = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        self.assertIn("error", result)
        self.assertIn("5 MB", result["error"])

    def test_patente_with_spaces_and_lowercase_resolves_equipment(self):
        result = self.env["ivess.workshop.news.intake"].create_ticket(
            **self._base_payload(patente=self._messy_plate())
        )
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.equipment_id, self.equipment)

    def test_unknown_patente_creates_ticket_without_equipment_and_warns(self):
        result = self.env["ivess.workshop.news.intake"].create_ticket(
            **self._base_payload(patente="ZZZ000")
        )
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertFalse(ticket.equipment_id)
        self.assertTrue(result["warnings"])

    def test_same_external_id_twice_does_not_duplicate(self):
        payload = self._base_payload(external_id="wa-8f2c1")
        first = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        second = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        self.assertFalse(first["already_registered"])
        self.assertTrue(second["already_registered"])
        self.assertEqual(first["ticket_id"], second["ticket_id"])

    def test_unknown_param_is_rejected(self):
        result = self.env["ivess.workshop.news.intake"].create_ticket(
            **self._base_payload(unexpected_field="x")
        )
        self.assertIn("error", result)
        self.assertIn("unexpected_field", result["error"])

    def test_html_in_observations_is_escaped_in_payload(self):
        payload = self._base_payload(observations="<script>alert(1)</script>")
        result = self.env["ivess.workshop.news.intake"].create_ticket(**payload)
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertNotIn("<script>", ticket.intake_payload)
        self.assertIn("&lt;script&gt;", ticket.intake_payload)
