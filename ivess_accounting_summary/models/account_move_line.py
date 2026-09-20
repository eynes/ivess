from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    x_origin_document_id = fields.Many2one(
        comodel_name="account.move",
        string="Documento de Origen",
        readonly=True,
        copy=False,
        index=True,
        help=(
            "Comprobante original (factura/recibo) que dio lugar a esta "
            "línea del asiento resumen mensual. Mantiene la trazabilidad "
            "de la deuda legal hacia el PDF de origen."
        ),
    )
    x_summary_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Neteada por Asiento",
        readonly=True,
        copy=False,
        index=True,
        help=(
            "Asiento de neteo del Asistente de Cierre Mensual que ya "
            "procesó esta línea. Evita que una nueva ejecución del "
            "asistente vuelva a sumarizarla."
        ),
    )
