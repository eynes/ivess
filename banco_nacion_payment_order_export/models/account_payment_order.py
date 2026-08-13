# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import fields, models


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    concepto_bna = fields.Selection(
        selection=[
            ('VAR', 'Varios'),
            ('ALQ', 'Alquileres'),
            ('CUO', 'Cuotas'),
            ('EXP', 'Expensas'),
            ('FAC', 'Factura'),
            ('PRE', 'Préstamo'),
            ('SEG', 'Seguros'),
            ('HON', 'Honorarios'),
        ],
        string='Concepto Banco Nación',
        default='FAC',
        help='Código de concepto exigido por Banco Nación para el '
        'archivo de transferencias masivas a proveedores.',
    )
