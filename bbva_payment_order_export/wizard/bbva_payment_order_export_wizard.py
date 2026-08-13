# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
import base64
import re
from decimal import Decimal

from odoo import _, fields, models
from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width import FixedWidth, moneyfmt
from odoo.exceptions import ValidationError

from .bbva_fixed_width_dicts import (
    REGISTRO_010,
    REGISTRO_020,
    REGISTRO_025,
    REGISTRO_090,
    REGISTRO_095,
)

# l10n_latam.identification.type.name -> código BBVA (Apéndice B.6).
IDENTIFICATION_TYPE_BBVA = {
    'CUIT': 'CUI',
    'CUIL': 'CUL',
    'DNI': 'DNI',
    'LE': 'LE',
    'LC': 'LC',
    'CDI': 'CDI',
}

# Código de provincia BBVA (Apéndice A.11): no tiene correspondencia con
# ningún campo de res.country.state, hay que mapearlo a mano.
PROVINCE_CODE_BBVA = {
    'base.state_ar_c': '01',  # Ciudad Autónoma de Buenos Aires
    'base.state_ar_b': '02',  # Buenos Aires
    'base.state_ar_k': '03',  # Catamarca
    'base.state_ar_x': '04',  # Córdoba
    'base.state_ar_w': '05',  # Corrientes
    'base.state_ar_h': '06',  # Chaco
    'base.state_ar_u': '07',  # Chubut
    'base.state_ar_e': '08',  # Entre Ríos
    'base.state_ar_p': '09',  # Formosa
    'base.state_ar_y': '10',  # Jujuy
    'base.state_ar_l': '11',  # La Pampa
    'base.state_ar_f': '12',  # La Rioja
    'base.state_ar_m': '13',  # Mendoza
    'base.state_ar_n': '14',  # Misiones
    'base.state_ar_q': '15',  # Neuquén
    'base.state_ar_r': '16',  # Río Negro
    'base.state_ar_a': '17',  # Salta
    'base.state_ar_j': '18',  # San Juan
    'base.state_ar_d': '19',  # San Luis
    'base.state_ar_z': '20',  # Santa Cruz
    'base.state_ar_s': '21',  # Santa Fe
    'base.state_ar_g': '22',  # Santiago del Estero
    'base.state_ar_t': '23',  # Tucumán
    'base.state_ar_v': '40',  # Tierra del Fuego
}


def _only_digits(value):
    return re.sub(r'\D', '', value or '')


class BbvaPaymentOrderExportWizard(models.TransientModel):
    _name = 'bbva.payment.order.export.wizard'
    _description = 'BBVA Payment Order Export Wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    payment_order_ids = fields.Many2many(
        comodel_name='account.payment.order',
        string='Órdenes de pago',
        domain="[('company_id', '=', company_id), ('type', '=', 'payment'), "
        "('state', '=', 'posted')]",
    )
    fecha_proceso = fields.Date(
        string='Fecha de proceso',
        required=True,
        default=fields.Date.context_today,
        help='Fecha hábil de proceso/envío del archivo (AAAAMMDD en el TXT).',
    )
    # Datos de la contratación de la cuenta de débito con BBVA. Por ahora
    # se piden en el wizard; a futuro deberían vivir en una configuración
    # persistente ligada al journal (ver sección 7.1 del análisis).
    suc_cta_debito = fields.Char(string='Sucursal cuenta débito', required=True)
    dv_cta_debito = fields.Char(
        string='Dígito verificador cuenta débito', required=True
    )
    nro_cta_debito = fields.Char(string='Número cuenta débito', required=True)
    contrato_prov = fields.Char(
        string='Contrato BBVA Pago a Proveedores', required=True
    )
    preview_txt = fields.Text(string='Vista previa', readonly=True)

    def _check_payment_orders(self):
        self.ensure_one()
        if not self.payment_order_ids:
            raise ValidationError(_('Seleccione al menos una orden de pago.'))
        other_company = self.payment_order_ids.filtered(
            lambda po: po.company_id != self.company_id
        )
        if other_company:
            raise ValidationError(
                _('Todas las órdenes de pago deben ser de la compañía %s.')
                % self.company_id.name
            )
        not_payment = self.payment_order_ids.filtered(lambda po: po.type != 'payment')
        if not_payment:
            raise ValidationError(
                _(
                    'Solo se pueden exportar órdenes de pago a proveedores: '
                    '%s no es de ese tipo.'
                )
                % ', '.join(not_payment.mapped('number'))
            )
        not_posted = self.payment_order_ids.filtered(lambda po: po.state != 'posted')
        if not_posted:
            raise ValidationError(
                _('Solo se pueden exportar órdenes de pago confirmadas: %s no lo está.')
                % ', '.join(not_posted.mapped('number'))
            )
        province_codes = self._province_code_map()
        errors = []
        for payment_order in self.payment_order_ids:
            errors += self._payment_order_errors(payment_order, province_codes)
        if errors:
            raise ValidationError('\n'.join(errors))

    def _payment_order_errors(self, payment_order, province_codes):
        errors = []
        checks = payment_order.issued_check_ids
        if len(checks) > 1:
            not_to_order = checks.filtered(
                lambda check: check.checkbook_format != 'physical'
                and check.not_order
            )
            if not_to_order:
                errors.append(
                    _(
                        '%s: tiene Echeqs "no a la orden" (%s); BBVA solo '
                        'admite Echeqs "a la orden" en el registro 025 '
                        '(multi-instrumento).'
                    )
                    % (payment_order.number, ', '.join(not_to_order.mapped('number')))
                )
        partner = payment_order.partner_id
        if not partner:
            errors.append(
                _('%s: no tiene proveedor/beneficiario asignado.')
                % payment_order.number
            )
            return errors
        argentina = self.env.ref('base.ar')
        if partner.country_id and partner.country_id != argentina:
            errors.append(
                _('%s: el proveedor %s no es de Argentina, fuera de alcance.')
                % (payment_order.number, partner.name)
            )
        missing = []
        if not partner.vat:
            missing.append(_('CUIT/CUIL'))
        if (
            partner.document_type_id.name
            not in IDENTIFICATION_TYPE_BBVA
        ):
            missing.append(_('tipo de documento'))
        if not partner.street:
            missing.append(_('calle'))
        if not partner.city:
            missing.append(_('localidad'))
        if not partner.zip:
            missing.append(_('código postal'))
        if partner.state_id.id not in province_codes:
            missing.append(_('provincia'))
        if not partner.email:
            missing.append(_('email'))
        if missing:
            errors.append(
                _('%(order)s (%(partner)s): faltan estos datos: %(fields)s.')
                % {
                    'order': payment_order.number,
                    'partner': partner.name,
                    'fields': ', '.join(missing),
                }
            )
        return errors

    def _province_code_map(self):
        codes = {}
        for xmlid, code in PROVINCE_CODE_BBVA.items():
            state = self.env.ref(xmlid, raise_if_not_found=False)
            if state:
                codes[state.id] = code
        return codes

    def _total_amount(self):
        return self._moneyfmt(sum(self.payment_order_ids.mapped('amount')))

    def _moneyfmt(self, amount):
        return moneyfmt(Decimal(str(amount)), places=2, ndigits=13, dp='')

    def _identification_type_bbva(self, partner):
        code = IDENTIFICATION_TYPE_BBVA.get(
            partner.document_type_id.name
        )
        if not code:
            raise ValidationError(
                _('El proveedor %s no tiene un tipo de documento soportado por BBVA.')
                % partner.name
            )
        return code

    def _forma_pago_bbva(self, check):
        return 'CH' if check.checkbook_format == 'physical' else 'EC'

    def _dispon_pago_bbva(self, check):
        # Tabla A.15 de ANALISIS_Y_DISENO.md: depende de si el cheque es de
        # pago diferido (CPD, códigos 0-3) o "al día" (códigos 4-7), y de la
        # combinación cruzado/a la orden.
        deferred = check.type == 'deferred'
        if check.crossed and check.not_order:
            return '0' if deferred else '4'
        if check.crossed and not check.not_order:
            return '1' if deferred else '5'
        if not check.crossed and not check.not_order:
            return '2' if deferred else '6'
        return '3' if deferred else '7'

    def _nro_cheque_bbva(self, check):
        number = _only_digits(check.number)
        if check.checkbook_id.format == 'virtual':
            # Regla BBVA: chequera virtual -> el número arranca con "8"
            # (validado carácter por carácter contra el archivo real
            # JUMI_OP_ECHEQS_2026-06-23.txt).
            return ('8' + number).ljust(13, '0')
        return number.rjust(13, '0')

    def _pro_nro_beneficiario(self, partner):
        # Punto abierto #1 (ver ANALISIS_Y_DISENO.md): se usa el id interno
        # del partner como identificador estable del proveedor, a falta de
        # una definición del cliente/banco.
        return str(partner.id).rjust(15, '0')

    def _pro_nro_ord(self):
        # PRO-NRO-ORD es constante para todas las líneas 020/090 de un mismo
        # archivo (validado contra JUMI_OP_ECHEQS_2026-06-23.txt: las 2 OPs
        # del ejemplo comparten el mismo valor) -- pese al nombre, no
        # identifica a la orden de pago individual, sino al lote/archivo.
        # Todavía no existe el modelo de trazabilidad de lote (sección B.9
        # del análisis); hasta que exista, se arma con fecha de proceso + id
        # del wizard.
        self.ensure_one()
        return self.fecha_proceso.strftime('%Y%m%d') + str(self.id).zfill(7)

    def _build_header_line(self):
        vals = {
            'ident_registro': '0306',
            'tipo_reg': '010',
            'tipo_doc_empresa': 'CUIT',
            'cuit_empresa': _only_digits(self.company_id.vat),
            'secuencia': '0',
            'moneda': '0',
            'importe_total': self._total_amount(),
            'forma_pago': '99',
            'forma_cobro': '0',
            'dispon_pago': '9',
            'deposito': '0',
            'fecha_emision': self.fecha_proceso.strftime('%Y%m%d'),
            'fecha_entrega': '99999999',
            'fecha_pago': '99999999',
            'entidad': '0017',
            'suc_cta_debito': _only_digits(self.suc_cta_debito),
            'dv_cta_debito': _only_digits(self.dv_cta_debito),
            'tipo_cta_debito': '01',
            'moneda_cta_debito': '0',
            'nro_cta_debito': _only_digits(self.nro_cta_debito),
            'cantidad_ordenes': str(len(self.payment_order_ids)),
            'fecha_proceso': self.fecha_proceso.strftime('%Y%m%d'),
            'contrato_prov': self.contrato_prov,
        }
        fixed_width = FixedWidth(REGISTRO_010)
        fixed_width.update(**vals)
        return fixed_width.line

    def _importe_020(self, payment_order, checks):
        # El importe del 020 es la suma de los cheques/Echeqs asociados
        # (los mismos que se detallan en cada 025); si la orden no tiene
        # ninguno, se usa el monto de la orden de pago.
        if checks:
            return sum(checks.mapped('amount'))
        return payment_order.amount

    def _build_020_line(self, payment_order, checks, row_number, pro_nro_ord):
        partner = payment_order.partner_id
        single_instrument = len(checks) == 1
        if not single_instrument:
            # Orden sin cheque asociado, o cancelada con más de uno: el 020
            # no informa un instrumento real (en el caso multi-instrumento
            # eso queda en cada 025), usa FORMA_PAGO=MP / DISPON_P=9 /
            # FECHA_PAGO=99999999 (ver Apéndice A.2/B.0.1 de
            # docs/ANALISIS_Y_DISENO.md, validado contra IMPA/LUFRAN).
            forma_pago = 'MP'
            dispon_p = '9'
            fecha_pago = '99999999'
            nro_cheque = '0'
        else:
            check = checks
            forma_pago = self._forma_pago_bbva(check)
            dispon_p = self._dispon_pago_bbva(check)
            fecha_pago = (payment_order.date_due or self.fecha_proceso).strftime(
                '%Y%m%d'
            )
            nro_cheque = self._nro_cheque_bbva(check)
        vals = {
            'ident_registro': '0306',
            'tipo_reg': '020',
            'tipo_doc_empresa': 'CUIT',
            'cuit_empresa': _only_digits(self.company_id.vat),
            'secuencia': str(row_number - 1),
            'pro_nro_beneficiario': self._pro_nro_beneficiario(partner),
            'nro_minuta': _only_digits(payment_order.number),
            'importe': self._moneyfmt(self._importe_020(payment_order, checks)),
            'pro_nro_ord': pro_nro_ord,
            'ipermfin': 'N',
            'cli_aje': ' ',
            'tipo_documento': self._identification_type_bbva(partner),
            'nro_documento': _only_digits(partner.vat),
            'suc_entrega': _only_digits(self.suc_cta_debito),
            'fecha_entrega': (
                payment_order.date_effective or self.fecha_proceso
            ).strftime('%Y%m%d'),
            'fecha_pago': fecha_pago,
            'forma_pago': forma_pago,
            'forma_cobro': '0',
            'dispon_p': dispon_p,
            'deposito': '0',
            'nro_cheque': nro_cheque,
        }
        fixed_width = FixedWidth(REGISTRO_020)
        fixed_width.update(**vals)
        return fixed_width.line

    def _build_025_line(self, payment_order, check, row_number):
        vals = {
            'ident_registro': '0306',
            'tipo_reg': '025',
            'tipo_doc_empresa': 'CUIT',
            'cuit_empresa': _only_digits(self.company_id.vat),
            'secuencia': str(row_number - 1),
            'nro_minuta': _only_digits(payment_order.number),
            'importe': self._moneyfmt(check.amount),
            'ipermfin': 'N',
            'fecha_pago': (check.payment_date or self.fecha_proceso).strftime(
                '%Y%m%d'
            ),
            'forma_pago': self._forma_pago_bbva(check),
            'dispon_p': self._dispon_pago_bbva(check),
            'nro_cheque': self._nro_cheque_bbva(check),
        }
        fixed_width = FixedWidth(REGISTRO_025)
        fixed_width.update(**vals)
        return fixed_width.line

    def _build_090_line(self, payment_order, row_number, pro_nro_ord, province_codes):
        partner = payment_order.partner_id
        vals = {
            'ident_registro': '0306',
            'tipo_reg': '090',
            'tipo_doc_empresa': 'CUIT',
            'cuit_empresa': _only_digits(self.company_id.vat),
            'secuencia': str(row_number - 1),
            'pro_nro_ord': pro_nro_ord,
            'pro_nro_benef': self._pro_nro_beneficiario(partner),
            'pro_est_benef': '1',
            'pro_docto_tip': self._identification_type_bbva(partner),
            'pro_docto_nro': _only_digits(partner.vat),
            'pro_denomina': partner.name or '',
            'pro_permit_finan': 'N',
            'pro_ingbrts': partner.nro_insc_iibb or '',
            'pro_calle': partner.street or '',
            'pro_localid': partner.city or '',
            'pro_cpostal': partner.zip or '',
            'pro_codprov': province_codes[partner.state_id.id],
            'pro_codpais': '080',
            'pro_email': partner.email or '',
            'pro_minuta': _only_digits(payment_order.number),
        }
        fixed_width = FixedWidth(REGISTRO_090)
        fixed_width.update(**vals)
        return fixed_width.line

    def _build_footer_line(self, line_count):
        vals = {
            'ident_registro': '0306',
            'tipo_reg': '095',
            'tipo_doc_empresa': 'CUIT',
            'cuit_empresa': _only_digits(self.company_id.vat),
            'secuencia': str(line_count - 1),
            'suma_importe': self._total_amount(),
            'cant_pagos': str(len(self.payment_order_ids)),
            'tot_reg': str(line_count),
        }
        fixed_width = FixedWidth(REGISTRO_095)
        fixed_width.update(**vals)
        return fixed_width.line

    def _build_lines(self):
        """Arma las líneas del archivo BBVA.

        Cada orden de pago aporta un 020 seguido, si tiene más de un
        cheque/Echeq asociado, de un 025 por cada instrumento adicional, y
        finalmente su 090 (ver docs/ANALISIS_Y_DISENO.md, Apéndice A.3/B.3).
        """
        self._check_payment_orders()
        province_codes = self._province_code_map()
        pro_nro_ord = self._pro_nro_ord()
        lines = [self._build_header_line()]
        row_number = 1
        for payment_order in self.payment_order_ids:
            checks = payment_order.issued_check_ids
            row_number += 1
            lines.append(
                self._build_020_line(payment_order, checks, row_number, pro_nro_ord)
            )
            if len(checks) > 1:
                for check in checks:
                    row_number += 1
                    lines.append(
                        self._build_025_line(payment_order, check, row_number)
                    )
            row_number += 1
            lines.append(
                self._build_090_line(
                    payment_order, row_number, pro_nro_ord, province_codes
                )
            )
        row_number += 1
        lines.append(self._build_footer_line(row_number))
        return lines

    def action_preview(self):
        self.ensure_one()
        self.preview_txt = '\n'.join(self._build_lines())
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
        filename = '{}_OP_ECHEQS_{}.txt'.format(
            re.sub(r'\W+', '', self.company_id.name or 'BBVA'),
            self.fecha_proceso.strftime('%Y-%m-%d'),
        )
        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(content.encode('latin-1')),
                'res_model': self._name,
                'res_id': self.id,
            }
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
