import base64

from odoo.tests.common import TransactionCase

FAKE_IMAGE_DATA = base64.b64encode(b"fake-image-bytes").decode()


class IntakeTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workshop_team = cls.env["helpdesk.team"].create({
            "name": "Taller Mecánico Test",
            "team_type": "workshop",
        })
        cls.refill_team = cls.env["helpdesk.team"].create({
            "name": "Recargas Test",
            "team_type": "refill",
        })
        cls.equipment = cls.env["maintenance.equipment"].create({
            "name": "PQU191",
        })
        cls.dispatch_number = cls.env["delivery.route.number"].create({})
        cls.dispatch_number_2 = cls.env["delivery.route.number"].create({})

    def _make_attachment(self, field, filename="foto.jpg", mimetype="image/jpeg", data=None):
        return {
            "field": field,
            "filename": filename,
            "mimetype": mimetype,
            "data": FAKE_IMAGE_DATA if data is None else data,
        }
