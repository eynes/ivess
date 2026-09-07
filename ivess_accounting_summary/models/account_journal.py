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
