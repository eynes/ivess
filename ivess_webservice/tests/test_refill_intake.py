from odoo.tests import tagged

from .common import IntakeTestCommon


@tagged("post_install", "-at_install")
class TestRefillIntake(IntakeTestCommon):
    def test_factory_refill_creates_ticket_without_maintenance_order(self):
        result = self.env["ivess.refill.intake"].create_ticket(
            refill_type="factory",
            dispatch=str(self.dispatch_number.number),
            vehicle_location="Av. Mitre 1200, Avellaneda",
            request="20 bidones 20L, 10 sifones",
        )
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.team_id, self.refill_team)
        self.assertEqual(ticket.refill_type, "factory")
        self.assertFalse(ticket.maintenance_order_ids)

    def test_street_refill_stores_both_dispatches(self):
        result = self.env["ivess.refill.intake"].create_ticket(
            refill_type="street",
            dispatch=str(self.dispatch_number.number),
            to_dispatch=str(self.dispatch_number_2.number),
            request="Entregado: 15 bidones 20L",
        )
        self.assertTrue(result.get("success"))
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.dispatch, str(self.dispatch_number.number))
        self.assertEqual(ticket.refill_to_dispatch, str(self.dispatch_number_2.number))
        self.assertEqual(ticket.refill_to_dispatch_id, self.dispatch_number_2)

    def test_same_origin_and_destination_dispatch_is_rejected(self):
        same = str(self.dispatch_number.number)
        result = self.env["ivess.refill.intake"].create_ticket(
            refill_type="street", dispatch=same, to_dispatch=same, request="algo"
        )
        self.assertIn("error", result)

    def test_invalid_refill_type_is_rejected(self):
        result = self.env["ivess.refill.intake"].create_ticket(
            refill_type="otro",
            dispatch=str(self.dispatch_number.number),
            vehicle_location="X",
            request="algo",
        )
        self.assertIn("error", result)

    def test_missing_refill_team_returns_clear_error(self):
        self.refill_team.unlink()
        result = self.env["ivess.refill.intake"].create_ticket(
            refill_type="factory",
            dispatch=str(self.dispatch_number.number),
            vehicle_location="X",
            request="algo",
        )
        self.assertIn("error", result)
        self.assertIn("refill", result["error"])
