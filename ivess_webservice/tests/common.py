import base64
import uuid

from odoo.tests.common import TransactionCase

FAKE_IMAGE_DATA = base64.b64encode(b"fake-image-bytes").decode()


class IntakeTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Estos tests corren tanto contra una 'devel' vacía como contra una
        # copia real (ej. ivess-31-8) que ya tiene su propio equipo 'workshop'
        # y patentes cargadas. Por eso la patente de prueba se genera única
        # por corrida (nunca puede matchear un registro real preexistente),
        # y no se asume que el equipo 'workshop'/'refill' usado por el
        # servicio sea el creado acá (el mixin busca por team_type, no por id).
        cls.workshop_team = cls.env["helpdesk.team"].create({
            "name": "Taller Mecánico Test",
            "team_type": "workshop",
        })
        cls.refill_team = cls.env["helpdesk.team"].create({
            "name": "Recargas Test",
            "team_type": "refill",
        })
        cls.plate = "ZT" + uuid.uuid4().hex[:8].upper()
        cls.equipment = cls.env["maintenance.equipment"].create({
            "name": cls.plate,
        })
        cls.dispatch_number = cls.env["delivery.route.number"].create({})
        cls.dispatch_number_2 = cls.env["delivery.route.number"].create({})

    def _messy_plate(self):
        """Misma patente de prueba, con espacios/guiones/minúsculas mezclados."""
        return f"{self.plate[:2].lower()}-{self.plate[2:].lower()}"

    def _make_attachment(self, field, filename="foto.jpg", mimetype="image/jpeg", data=None):
        return {
            "field": field,
            "filename": filename,
            "mimetype": mimetype,
            "data": FAKE_IMAGE_DATA if data is None else data,
        }
