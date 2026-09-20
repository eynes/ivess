from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    x_summarize_on_report = fields.Boolean(
        string="Sumarizar en Reporte",
        help=(
            "Al imprimir el asiento resumen mensual en el Diario de "
            "Refundición (Legal), colapsa todas las líneas de esta cuenta "
            "en un único monto totalizador."
        ),
    )
    x_legal_debt_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Deuda Legal",
        help=(
            "Solo aplica a cuentas de deudores/acreedores operativas (ej. "
            "'Deudores por Ventas'). Cuenta equivalente del Diario Legal a "
            "la que el Asistente de Cierre Mensual traslada el saldo "
            "pendiente de cada partner al refundir el período, dejando "
            "cerrada por resumen la cuenta operativa."
        ),
    )
    x_legal_bridge_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Puente (Cobrado en el Período)",
        help=(
            "Solo aplica a cuentas de deudores/acreedores operativas con "
            "Cuenta de Deuda Legal configurada. Cuenta técnica de enlace "
            "donde el Asistente de Cierre Mensual imputa, de forma "
            "agregada (sin desglose por partner), la porción de las "
            "facturas del período que ya fue cobrada/pagada antes del "
            "cierre: esa porción no genera deuda legal, pero su venta e "
            "impuestos igual deben reconocerse en el Diario Legal."
        ),
    )
