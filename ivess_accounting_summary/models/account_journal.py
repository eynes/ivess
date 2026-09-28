from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    x_is_legal_journal = fields.Boolean(
        string="Diario Legal (Refundición / Cierre)",
        help=(
            "Marca este diario como parte del libro legal rubricado "
            "(Diario de Refundición y/o Cierre de Ejercicio). Solo los "
            "asientos de estos diarios reciben folio legal correlativo "
            "(x_folio_legal) y solo ellos pueden usarse como diario "
            "destino en el Asistente de Cierre Mensual."
        ),
    )
    x_is_operational_journal = fields.Boolean(
        string="Diario Operativo (Cierre Mensual)",
        help=(
            "Marca este diario como candidato para el Asistente de Cierre "
            "Mensual: solo los diarios marcados acá aparecen para elegir "
            "como Diarios Operativos a Resumir. Evita resumir por "
            "accidente diarios con historial real no pensado para pasar "
            "por este proceso."
        ),
    )
