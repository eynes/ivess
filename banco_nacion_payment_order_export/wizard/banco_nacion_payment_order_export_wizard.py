# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
import base64
import re

from odoo import _, fields, models
from odoo.exceptions import ValidationError

CONCEPTO_BNA_LABELS = {
    'VAR': 'Varios',
    'ALQ': 'Alquileres',
    'CUO': 'Cuotas',
    'EXP': 'Expensas',
    'FAC': 'Factura',
    'PRE': 'Préstamo',
    'SEG': 'Seguros',
    'HON': 'Honorarios',
}

BNA_CSV_HEADER = 'CBU_CREDITO;IMPORTE;CONCEPTO;REFERENCIA;EMAIL'


def _format_amount_bna(amount):
    # Formato Banco Nación: punto de miles, coma decimal (ej. 1270.0 ->
    # "1.270,00"). El translate() reemplaza cada carácter según el mapeo de
    # una sola vez, así que no hay riesgo de que un "," recién puesto se
    # vuelva a traducir a ".".
    return '{:,.2f}'.format(amount).translate(str.maketrans({',': '.', '.': ','}))


def _normalize_reference(reference):
    return re.sub(r'[^A-Za-z0-9]', '', reference or '')


class BancoNacionPaymentOrderExportWizard(models.TransientModel):
    _name = 'banco.nacion.payment.order.export.wizard'
    _description = 'Banco Nación Payment Order Export Wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    payment_order_ids = fields.Many2many(
        comodel_name='account.payment.order',
        relation='banco_nacion_export_wizard_payment_order_rel',
        string='Órdenes de pago',
        domain="[('company_id', '=', company_id), ('type', '=', 'payment'), "
        "('state', '=', 'posted')]",
    )
    bank_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario/Cuenta Banco Nación',
        domain="[('company_id', '=', company_id), ('type', '=', 'bank')]",
        required=True,
        help='Diario cuyas líneas de método de pago se exportan como '
        'transferencia a Banco Nación. El importe exportado de cada orden '
        'es la suma de sus líneas de pago que usan este diario, no el '
        'total de la orden.',
    )
    preview_csv = fields.Text(string='Vista previa', readonly=True)

    def _check_payment_orders(self):
        self.ensure_one()
        if not self.payment_order_ids:
            raise ValidationError(_('Seleccione al menos una orden de pago.'))
        errors = []
        for payment_order in self.payment_order_ids:
            errors += self._payment_order_errors(payment_order)
        if errors:
            raise ValidationError('\n'.join(errors))

    def _payment_order_errors(self, payment_order):
        errors = []
        if payment_order.company_id != self.company_id:
            errors.append(
                _('%s: no pertenece a la compañía %s.')
                % (payment_order.number, self.company_id.name)
            )
        if payment_order.type != 'payment':
            errors.append(
                _('%s: solo se pueden exportar órdenes de pago a proveedores.')
                % payment_order.number
            )
        if payment_order.state != 'posted':
            errors.append(
                _(
                    '%s: solo se pueden exportar órdenes confirmadas '
                    '(está en estado "%s").'
                )
                % (payment_order.number, payment_order.state)
            )
        partner = payment_order.partner_id
        if not partner:
            errors.append(_('%s: no tiene proveedor asignado.') % payment_order.number)
        else:
            errors += self._partner_errors(payment_order, partner)
        errors += self._amount_errors(payment_order)
        if not payment_order.concepto_bna:
            errors.append(
                _('%s: no tiene seleccionado el Concepto Banco Nación.')
                % payment_order.number
            )
        elif payment_order.concepto_bna not in CONCEPTO_BNA_LABELS:
            errors.append(
                _('%s: el concepto "%s" no es un código admitido por Banco Nación.')
                % (payment_order.number, payment_order.concepto_bna)
            )
        errors += self._reference_errors(payment_order)
        return errors

    def _partner_errors(self, payment_order, partner):
        errors = []
        if not partner.cbu:
            errors.append(
                _('%s: el proveedor %s no tiene CBU informado.')
                % (payment_order.number, partner.name)
            )
        elif not re.fullmatch(r'\d{22}', partner.cbu):
            errors.append(
                _(
                    '%s: el CBU del proveedor %s no tiene 22 dígitos '
                    'numéricos ("%s").'
                )
                % (payment_order.number, partner.name, partner.cbu)
            )
        return errors

    def _amount_errors(self, payment_order):
        errors = []
        bna_lines = payment_order.payment_mode_line_ids.filtered(
            lambda line: line.payment_mode_id == self.bank_journal_id
        )
        if not bna_lines:
            errors.append(
                _(
                    '%s: no tiene ninguna línea de pago con el diario "%s" '
                    '(Banco Nación).'
                )
                % (payment_order.number, self.bank_journal_id.name)
            )
        elif sum(bna_lines.mapped('amount')) <= 0:
            errors.append(
                _('%s: el importe a transferir por Banco Nación es cero o negativo.')
                % payment_order.number
            )
        return errors

    def _reference_errors(self, payment_order):
        errors = []
        normalized = _normalize_reference(payment_order.reference)
        if not normalized:
            errors.append(
                _('%s: no tiene Ref. Pago informada.') % payment_order.number
            )
        elif len(normalized) > 12:
            errors.append(
                _(
                    '%s: la Ref. Pago "%s" supera los 12 caracteres una vez '
                    'quitados espacios y caracteres especiales ("%s").'
                )
                % (payment_order.number, payment_order.reference, normalized)
            )
        return errors

    def _bna_amount(self, payment_order):
        bna_lines = payment_order.payment_mode_line_ids.filtered(
            lambda line: line.payment_mode_id == self.bank_journal_id
        )
        return sum(bna_lines.mapped('amount'))

    def _build_line(self, payment_order):
        partner = payment_order.partner_id
        return ';'.join(
            [
                partner.cbu,
                _format_amount_bna(self._bna_amount(payment_order)),
                payment_order.concepto_bna,
                _normalize_reference(payment_order.reference),
                partner.email or '',
            ]
        )

    def _build_lines(self):
        self._check_payment_orders()
        lines = [BNA_CSV_HEADER]
        for payment_order in self.payment_order_ids:
            lines.append(self._build_line(payment_order))
        return lines

    def action_preview(self):
        self.ensure_one()
        self.preview_csv = '\n'.join(self._build_lines())
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        self.ensure_one()
        content = ''.join(line + '\r\n' for line in self._build_lines())
        filename = 'BancoNacion_Transferencias_{}_{}.csv'.format(
            re.sub(r'\W+', '', self.company_id.name or 'BNA'),
            fields.Date.context_today(self).strftime('%Y-%m-%d'),
        )
        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(content.encode('utf-8')),
                'res_model': self._name,
                'res_id': self.id,
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
