# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    banco_nacion_is_default_account = fields.Boolean(
        string='Cuenta predeterminada para exportar a Banco Nación',
        help='El asistente de exportación a Banco Nación usa esta cuenta '
        'como "Diario/Cuenta Banco Nación" cuando se elige esta compañía. '
        'Debe haber a lo sumo una cuenta marcada por compañía.',
    )
