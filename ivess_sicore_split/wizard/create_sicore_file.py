import binascii
import codecs
import logging
import re
import tempfile

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width import FixedWidth
from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width_dicts import (
    HEAD_LINES,
    HEAD_LINES_EXTERIOR,
)

_logger = logging.getLogger(__name__)

# Mismas etiquetas que create.sicore.files usa para el nombre de archivo,
# una por cada account.tax.retention_type que se exporta por separado.
RETENTION_TYPE_LABELS = {
    'vat': 'IVA',
    'profit': 'GANANCIAS',
}


class CreateSicoreFiles(models.TransientModel):
    _inherit = 'create.sicore.files'

    def _format_monetary(self, value):
        """T16639: separador decimal punto en vez de coma."""
        return "{:,.2f}".format(value).replace(",", "")

    def _get_perception_afip_code(self, perception_tax):
        """T16639: preferir el código cargado directo en la percepción.

        Si `sicore_tax_code` no está configurado, se sigue usando el
        lookup por el diario vinculado (comportamiento previo), para no
        romper percepciones que todavía no se migraron al campo nuevo.
        """
        if perception_tax.sicore_tax_code:
            return int(perception_tax.sicore_tax_code)
        return super()._get_perception_afip_code(perception_tax)

    def _generate_retention_file(
        self,
        retention_ids,
        exterior=False,
        perception_ids=None,
        retention_type_label='',
    ):
        """Copia de create.sicore.files._generate_retention_file (l10n_ar_eynes)
        con el nombre de archivo separado por tipo de retención (T16639).
        """
        head_file_errors = []
        head_regs = []
        fixed_width = (
            FixedWidth(HEAD_LINES)
            if not exterior
            else FixedWidth(HEAD_LINES_EXTERIOR)
        )
        is_local = not exterior

        tax_lines = self.env['account.payment.order.retention.line'].browse(
            retention_ids
        )

        # Filtrar lineas según si es local o no, para sacar los archivos separados.
        if is_local:
            filtered_tax_lines = tax_lines.filtered(
                lambda line: line.partner_id.property_account_position_id.local
            )
        else:
            filtered_tax_lines = tax_lines.filtered(
                lambda line: not line.partner_id.property_account_position_id.local
            )

        for tax_line in filtered_tax_lines:
            line_ident = 'Retention Tax Line #%s of Voucher #%s (%s)' % (
                tax_line.id,
                tax_line.payment_order_id,
                tax_line.payment_order_id.reference,
            )
            _logger.info(line_ident)
            date_voucher = tax_line.payment_order_id.date.strftime(
                '%d/%m/%Y'
            )  # Datetime->String: dd/mm/yyyy
            tipo_doc_retenido = str(
                tax_line.partner_id.document_type_id.afip_code
            )
            nro_doc_retenido = tax_line.partner_id.vat

            # First search in number then in reference
            internal_number = tax_line.payment_order_id.number or ''
            if not internal_number:
                err = '%s: Número de comprobante no encontrado.' % line_ident
                head_file_errors.append(err)
                continue
            else:
                internal_number = int(re.sub(r"\D", "", internal_number))

            date_emited = tax_line.date.strftime('%d/%m/%Y')

            exclusion_date_certificate = tax_line.exclusion_date_certificate
            if exclusion_date_certificate:
                exclusion_date_certificate = (
                    exclusion_date_certificate.strftime('%d/%m/%Y')
                )
            else:
                exclusion_date_certificate = ''

            porcentaje_exclusion = tax_line.excluded_percent * 100

            # Importe del comprobante: como 'codigo_comprobante' es siempre
            # '06' (orden de pago), el importe que corresponde informar es el
            # total de la OP, incluyendo las retenciones.
            amount_total = tax_line.payment_order_id.amount
            base_amount = tax_line.base_amount
            ret_aplicada = tax_line.amount  # Importe retenido
            nro_cert_propio = re.sub('[-]', '', tax_line.certificate_no or '')
            reg_code = (
                tax_line.reg_code
                or tax_line.taxapp_id.reg_code
                or tax_line.concept_id.code
            )
            reg_code = str(reg_code)[:3] if reg_code else False
            if not reg_code:
                reg_code = 0
            tax_journal = self.env['account.journal'].search(
                [('tax_id', '=', tax_line.retention_id.id)]
            )
            codigo_impuesto = (
                int(tax_journal.afip_code) if tax_journal.afip_code else 0
            )
            if not codigo_impuesto:
                raise UserError(
                    _(
                        "Error: Add field 'afip code' to retention\n"
                        "(Accounting->Configuration->Retentions->%s->AFIP Code)"
                    )
                    % tax_journal.name
                )
            line = {
                'codigo_comprobante': '06',
                # 06: Orden de pago; HARD: Todas las ret. salen de una op
                'fecha_emision': date_voucher,
                'numero_comprobante': internal_number,
                'monto_comprobante': self._format_monetary(amount_total),
                'codigo_impuesto': codigo_impuesto,
                'codigo_regimen': reg_code,
                'codigo_operacion': 1,  # Cod. Retenciones
                'base_calculo': self._format_monetary(base_amount),
                'fecha_emision_retenc': date_emited,
                'codigo_condicion': '01',  # Inscripto (HARD: Segun longport)
                'sujetos_suspend': '',  # Beneficiarios en el exterior
                'importe_retencion': self._format_monetary(ret_aplicada),
                'porcentaje_exclusion': self._format_monetary(
                    porcentaje_exclusion
                ),
                'fecha_emision_boletin': (
                    date_emited if porcentaje_exclusion != 0 else ""
                ),  # Solo si hay exclusion
                'tipo_documento_retenido': tipo_doc_retenido,
                'numero_documento_retenido': nro_doc_retenido,
                'numero_certificado_original': nro_cert_propio,
                'denominacion_ordenante': (
                    '' if is_local else tax_line.partner_id.name[:30]
                ),
                'acrecentamiento': '' if is_local else '0',  # Segun longport
                'cuit_pais_retenido': '' if is_local else '',  # TODO
                'cuit_ordenante': '' if is_local else '',  # TODO
            }

            # Apendeamos el registro
            fixed_width.update(**line)
            head_regs.append(fixed_width.line)

        # Las percepciones se informan siempre en el archivo local: el layout
        # de exterior pide datos del ordenante que la percepcion no tiene.
        if is_local and perception_ids:
            perception_errors, perception_regs = self._get_perception_regs(
                fixed_width, perception_ids
            )
            head_file_errors += perception_errors
            head_regs += perception_regs

        # Chequeamos si hubo errores
        if len(head_file_errors):
            return head_file_errors, False

        # Retornar vacio si no hay lineas generadas
        if len(head_regs) < 1:
            return [], False

        head_filename = tempfile.mkstemp(suffix='.sicore')[1]
        f = codecs.open(head_filename, "w", "latin-1")

        for r in head_regs:
            r2 = [a for a in r]
            try:
                f.write(''.join(r2))
            except Exception as e:
                raise e
            f.write('\r\n')

        f.close()

        f = open(head_filename, 'rb')  # rb to export with CRLF line terminators

        # T16639: un nombre base por tipo de retencion (IVA/Ganancias), en
        # vez de un unico archivo mezclando ambos tipos.
        name_base = "SICORE_RET" if is_local else "SICORE_RET_EXT"
        if retention_type_label:
            name_base += "_%s" % retention_type_label
        name = ('%s_%s_%s.txt') % (
            name_base,
            self.period_start,
            self.company_id.name.replace(' ', '-'),
        )
        generated_file_rec = self.env['sicore.generated.files'].create(
            {
                'code': name,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'presentation_date': self.presentation_date,
                'company_id': self.company_id.id,
            }
        )
        data = f.read()
        if isinstance(data, str):
            data = data.encode('ascii', 'replace')
        data_attach = {
            'name': name,
            'datas': binascii.b2a_base64(data),
            'store_fname': name,
            'res_model': 'sicore.generated.files',
            'res_id': generated_file_rec.id,
        }
        new_attachment = self.env['ir.attachment'].create(data_attach)
        generated_file_rec.write({'attachment_id': new_attachment.id})
        f.close()

        return [], True

    def create_files(self):
        """Copia de create.sicore.files.create_files (l10n_ar_eynes) que
        separa las retenciones de IVA y de Ganancias en archivos distintos
        (T16639), en vez de mezclarlas en el mismo archivo.
        """
        self._validate_before_create()

        errors = ''
        cr = self.env.cr

        retention_query = (
            "SELECT r.id, at.retention_type "
            "FROM account_payment_order_retention_line r "
            "JOIN account_tax at ON r.retention_id=at.id "
            "JOIN account_payment_order av ON av.id=r.payment_order_id "
            "WHERE r.date BETWEEN %(date_from)s AND %(date_to)s "
            "AND at.retention_type in ('vat','profit') AND at.type_tax_use='purchase' "
            "AND av.state ~ 'posted' AND r.company_id = %(company_id)s "
            "ORDER BY r.date"
        )

        cr.execute(
            retention_query,
            {
                'date_from': self.period_start,
                'date_to': self.period_end,
                'company_id': self.company_id.id,
            },
        )
        res = cr.fetchall()
        retention_ids_by_type = {'vat': [], 'profit': []}
        for retention_id, retention_type in res:
            retention_ids_by_type[retention_type].append(retention_id)

        perception_ids = []
        if self.include_vat_perceptions:
            perception_ids = self._search_perception_ids()

        if not res and not perception_ids:
            message = _(
                """Export Error
                    Applicable Retentions for export not found.
                    HINT:
                    The retention is of type vat or profit ?"""
            )
            if self.include_vat_perceptions:
                message += _(
                    "\nNo VAT perceptions were found either. "
                    "Are the invoices with perceptions posted?"
                )
            raise UserError(message)

        errors_by_file = {}
        success_labels = []
        for retention_type, label in RETENTION_TYPE_LABELS.items():
            type_retention_ids = retention_ids_by_type[retention_type]
            type_perception_ids = (
                perception_ids if retention_type == 'vat' else None
            )
            if not type_retention_ids and not type_perception_ids:
                continue

            local_errors, success_local = self._generate_retention_file(
                type_retention_ids,
                perception_ids=type_perception_ids,
                retention_type_label=label,
            )
            ext_errors, success_ext = self._generate_retention_file(
                type_retention_ids,
                exterior=True,
                retention_type_label=label,
            )

            if local_errors or ext_errors:
                errors_by_file[label] = local_errors + ext_errors
            if success_local:
                success_labels.append(label)
            if success_ext:
                success_labels.append('%s EXT' % label)

        for label, file_errors in errors_by_file.items():
            errors += _('Retention File Errors (%s)\n================\n') % label
            errors += '\n'.join(file_errors) + '\n'

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref('l10n_ar_eynes.view_create_sicore_files').id
            res = {
                'name': _('Sicore'),
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.sicore.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        elif success_labels:
            message = _("SICORE Reports created: %s ") % (
                ', '.join(success_labels)
            )
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': message,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
            return notification
        else:
            res = True

        return res

    def create_files_rrhh(self):
        """Copia de create.sicore.files.create_files_rrhh (l10n_ar_eynes)
        con un fix a la query de payslips: 'company_id' vive en
        hr_payslip (pl), no en hr_payslip_line (psl) -- el original
        filtraba `psl.company_id`, que no existe como columna y rompe
        con `UndefinedColumn`. Encontrado probando T16639, sin relacion
        con el split de archivos.
        """
        self._validate_before_create()

        rrhh_code = self.rrhh_ret_profit_code
        if not rrhh_code:
            raise ValidationError(_('Invalid RRHH Code.'))
        if not (
            self._table_exists('hr_payslip')
            and self._table_exists('hr_payslip_line')
        ):
            raise UserError(
                _(
                    'Export Error\n'
                    'The RRHH SICORE export requires the Payroll module '
                    'to be installed in this database.'
                )
            )
        errors = ''

        q = """
            SELECT pl.id payslip_id, pl.employee_id employee_id,
            SUM(psl.total) total FROM hr_payslip_line AS psl
            JOIN hr_payslip AS pl ON (pl.id=psl.slip_id)
            WHERE psl.code IN %(code)s AND pl.date BETWEEN
            %(date_from)s AND %(date_to)s AND psl.total!=0
            AND pl.state IN %(state)s AND pl.company_id = %(company_id)s
            GROUP BY pl.id, pl.employee_id, pl.date_to
        """
        q_params = {
            'state': tuple(['done']),
            'code': tuple([self.rrhh_ret_profit_code, 'H349']),
            'date_from': self.period_start,
            'date_to': self.period_end,
            'company_id': self.company_id.id,
        }
        self.env.cr.execute(q, q_params)
        res = self.env.cr.fetchall()
        if not len(res):
            raise UserError(
                _(
                    """Export Error
                    Applicable Retentions for export based on rule %s not found.
                    HINT: The payslips are in state done?"""
                )
                % self.rrhh_ret_profit_code
            )

        for r in range(len(res)):
            aux_tuple = (self.presentation_date,)
            res[r] = res[r] + aux_tuple

        retention_errors = self._generate_retention_file_rrhh(res)

        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_errors)

        if errors:
            self.write({'notes': errors})
            form_id = self.env.ref('l10n_ar_eynes.view_create_sicore_files').id
            res = {
                'name': _('Sicore'),
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.sicore.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            res = True

        return res
