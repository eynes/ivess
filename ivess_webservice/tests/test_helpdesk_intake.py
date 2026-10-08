from odoo.tests import tagged

from .common import IntakeTestCommon


@tagged("post_install", "-at_install")
class TestHelpdeskIntake(IntakeTestCommon):
    def _create(self, **overrides):
        payload = {
            "patente": self.plate,
            "dispatch": str(self.dispatch_number.number),
            "items": [{"Nivel fluido": "Mal"}],
        }
        payload.update(overrides)
        return self.env["ivess.helpdesk.intake"].create_ticket(**payload)

    def test_ticket_name_with_non_observation_item_shows_name_and_value(self):
        result = self._create()
        self.assertEqual(
            result["ticket_name"],
            f"Rep. {self.dispatch_number.number} · Chequeo · Nivel fluido: Mal · {self.plate}",
        )

    def test_ticket_name_with_observation_shows_driver_text_only(self):
        result = self._create(items=[{" Observaciones ": "no andan las luces de freno"}])
        self.assertEqual(
            result["ticket_name"],
            f"Rep. {self.dispatch_number.number} · Chequeo · no andan las luces de freno · {self.plate}",
        )

    def test_ticket_name_with_several_items_joins_them_with_comma(self):
        result = self._create(
            items=[{"Nivel fluido": "Mal"}, {"Presion cubiertas": "Baja"}, {"Observaciones": "ok"}]
        )
        self.assertEqual(
            result["ticket_name"],
            f"Rep. {self.dispatch_number.number} · Chequeo · "
            f"Nivel fluido: Mal, Presion cubiertas: Baja, ok · {self.plate}",
        )

    def test_ticket_name_without_dispatch_starts_with_type(self):
        result = self._create(dispatch="")
        self.assertEqual(result["ticket_name"], f"Chequeo · Nivel fluido: Mal · {self.plate}")

    def test_ticket_name_uses_raw_dispatch_even_if_route_does_not_exist(self):
        result = self._create(dispatch="987654")
        self.assertEqual(
            result["ticket_name"], f"Rep. 987654 · Chequeo · Nivel fluido: Mal · {self.plate}"
        )
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.dispatch, "987654")
        self.assertFalse(ticket.dispatch_id)
