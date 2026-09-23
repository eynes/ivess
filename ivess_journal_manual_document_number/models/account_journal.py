from odoo import fields, models


class _ManualDocumentSequence:
    """Stand-in for an ir.sequence record, used when the journal forces
    manual document numbering.

    ``AccountMove._post()`` (l10n_ar_eynes) always calls
    ``journal.get_sequence_from_invoice(invoice)._next()`` and writes the
    result into ``internal_number``, consuming a real ir.sequence number in
    the process. Returning this instead keeps the invoice's own
    (user-entered) ``internal_number`` and avoids burning a sequence number
    that would otherwise show up as a gap in the AFIP-facing numbering.
    """

    def __init__(self, value):
        self._value = value

    def _next(self):
        return self._value


class AccountJournal(models.Model):
    _inherit = "account.journal"

    ivess_force_manual_document_number = fields.Boolean(
        string="Forzar numeración manual",
        help="Si está activo, el número de las facturas de cliente de este "
        "diario se ingresa a mano y no se completa automáticamente con el "
        "prefijo y la secuencia del diario al validar, igual que en una "
        "factura de proveedor.",
    )

    def get_sequence_from_invoice(self, invoice):
        if self.ivess_force_manual_document_number and invoice.move_type in (
            "out_invoice",
            "out_refund",
        ):
            return _ManualDocumentSequence(invoice.internal_number)
        return super().get_sequence_from_invoice(invoice)
