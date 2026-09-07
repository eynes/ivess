from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_folio_legal = fields.Char(
        string="Folio Legal",
        readonly=True,
        copy=False,
        help=(
            "Número de folio correlativo del libro diario legal, asignado "
            "por el proceso de foliación. Se asigna únicamente a los "
            "asientos del Diario de Refundición y de Cierre de Ejercicio, "
            "de forma independiente al número de asiento de gestión."
        ),
    )
    x_is_summary_entry = fields.Boolean(
        string="Es Asiento de Resumen/Neteo",
        readonly=True,
        copy=False,
        help=(
            "Asiento generado por el Asistente de Cierre Mensual (el "
            "neteo en el diario operativo o el resumen en el diario "
            "legal), no un comprobante operativo original."
        ),
    )
    x_closed_by_summary_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Cerrado por Resumen",
        readonly=True,
        copy=False,
        help=(
            "Asiento resumen del Diario Legal que trasladó el saldo "
            "pendiente de este comprobante a la cuenta de deuda legal. "
            "Un comprobante con este campo asignado está 'Cerrado por "
            "Resumen': su cobranza/pago debe gestionarse a partir de aquí "
            "contra la línea correspondiente de ese asiento resumen."
        ),
    )

    def _ivess_renumber_legal_folio(self, company):
        """Renumera x_folio_legal sin huecos para los diarios legales de `company`.

        Recalcula desde cero, en orden de fecha, la numeración de TODOS los
        asientos posteados de los diarios marcados x_is_legal_journal. Al
        ser un recálculo completo e idempotente, nunca deja huecos ni
        saltos, sin importar cuántas veces se ejecute ni qué haya pasado
        en los diarios operativos.
        """
        moves = self.search(
            [
                ("company_id", "=", company.id),
                ("journal_id.x_is_legal_journal", "=", True),
                ("state", "=", "posted"),
            ],
            order="date asc, id asc",
        )
        for index, move in enumerate(moves, start=1):
            folio = f"{index:06d}"
            if move.x_folio_legal != folio:
                move.x_folio_legal = folio
        return len(moves)
