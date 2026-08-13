# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bbva_is_default_debit_account = fields.Boolean(
        string='Cuenta predeterminada para exportar a BBVA',
        help='El asistente de exportación BBVA Pago a Proveedores usa esta '
        'cuenta para autocompletar los datos de la cuenta de débito cuando '
        'se elige esta compañía. Debe haber a lo sumo una cuenta marcada '
        'por compañía.',
    )
    bbva_suc_cta_debito = fields.Char(string='BBVA: sucursal cuenta débito')
    bbva_dv_cta_debito = fields.Char(
        string='BBVA: dígito verificador cuenta débito'
    )
    bbva_nro_cta_debito = fields.Char(string='BBVA: número cuenta débito')
    bbva_contrato_prov = fields.Char(
        string='BBVA: contrato Pago a Proveedores'
    )
