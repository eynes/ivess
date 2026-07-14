import logging
from collections import defaultdict

from odoo import _, models
from odoo.addons.l10n_ar_eynes.wizard.account_tax_subjournal_apportionable import (
    _clean_tax_name,
)
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountTaxSubjournalApportionableWizard(models.TransientModel):
    """Fix: el IVA al 0% (is_exempt=True, o alicuota 0%) no cuenta como
    Exento en el subdiario si la linea/producto no tiene 'fiscal_credit'
    cargado. Ese campo no aplica al IVA 0% (no hay credito fiscal que
    prorratear) y l10n_ar_fiscal_credit_ivess lo deja opcional para esos
    casos, por lo que el reporte original lo descartaba en silencio.
    """

    _inherit = 'account.tax.subjournal.apportionable.wizard'

    def _group_lines_data(self, cols, vat_cols):  # noqa: C901
        query_vals = self._get_line_vals()
        if not len(query_vals):
            raise UserError(_('There were no moves for this period'))

        c_taxes = [0] * len(cols)
        final_consumer_id = self.env.ref('l10n_ar_eynes.fiscal_position_cf').id
        ri_id = self.env.ref('l10n_ar_eynes.fiscal_position_ri').id

        lines = {}
        last_line_id = -1
        retention_perception_summary = {}
        for line in query_vals:
            is_final_consumer = line['fpid'] == final_consumer_id
            based_sign = 1

            if self.based_on == 'purchase':
                based_sign = -1

            invoice_type = self._get_invoice_type(
                line['voucher_type'], line['denomination']
            )
            key = line['invoice_id']
            line_id = line['line_id']
            amount = (line['credit'] - line['debit']) * based_sign

            if (
                self.grouped
                and is_final_consumer
                and line['invoice_total'] < self.grouped_max_amount
            ):
                key = 'cf' + line['date'].strftime('%d/%m/%Y') + invoice_type
                lines.setdefault(
                    key,
                    {
                        'invoice_number': '',
                        'date': line['date'],
                        'invoice_type': invoice_type,
                        'partner_name': 'Agrupado CF monto menor a %s'
                        % round(self.grouped_max_amount, 2),
                        'partner_vat': '',
                        'partner_ri': False,
                        'total': 0.0,
                        'taxes': [0] * len(cols),
                        'vat_taxes': {},
                        'no_taxed': 0.0,
                    },
                )
            else:
                lines.setdefault(
                    key,
                    {
                        'invoice_number': line['invoice_number'],
                        'date': line['date'],
                        'invoice_type': invoice_type,
                        'partner_name': line['partner'],
                        'partner_vat': line['vat'],
                        'partner_ri': line['fpid'] == ri_id,
                        'total': 0.0,
                        'taxes': [0] * len(cols),
                        'vat_taxes': {},
                        'no_taxed': 0.0,
                    },
                )

            if last_line_id != line_id:
                last_line_id = line_id
                lines[key]['total'] += amount

            for i, tax in enumerate(cols):
                if self.perception_retention_grouped:
                    tax_ids = tax.get('ids', False)
                    if tax_ids:
                        if line['tax_line_id'] in tax_ids:
                            tax_index = tax_ids.index(line['tax_line_id'])
                            # LINEA DE IMPUESTO
                            lines[key]['taxes'][i] += amount
                            retention_perception_summary.setdefault(
                                line['tax_line_id'],
                                [tax.get('names', [])[tax_index], 0.0],
                            )
                            retention_perception_summary[line['tax_line_id']][
                                1
                            ] += amount
                        if lines[key]['taxes'][i] != 0:
                            c_taxes[i] += 1

                if (
                    # LINEA DE IMPUESTO
                    line['tax_line_id'] == tax['id']
                    and tax['type'] == 'tax'
                ) or (
                    # LINEA DE PRODUCTO (BASE DE IMPUESTO)
                    line['tax_ids'] == tax['id']
                    and tax['type'] == 'base'
                ):
                    lines[key]['taxes'][i] += amount
                    if lines[key]['taxes'][i] != 0:
                        c_taxes[i] += 1

            for _i, tax in enumerate(vat_cols):
                tax_id = tax.get('id', -1)
                if (
                    # LINEA DE PRODUCTO (BASE DE IMPUESTO)
                    line['tax_ids']
                    == tax_id
                ):
                    lines[key]['vat_taxes'].setdefault(
                        tax_id,
                        {
                            'name': _clean_tax_name(tax.get('name', '')),
                            # FIX: se necesita saber si el impuesto es
                            # Exento para no depender solo del nombre.
                            'is_exempt': tax.get('is_exempt', False),
                        },
                    )
                    lines[key]['vat_taxes'][tax_id].setdefault(
                        line['fiscal_credit'], 0.0
                    )
                    lines[key]['vat_taxes'][tax_id][
                        line['fiscal_credit']
                    ] += amount

            if not (line['tax_line_id'] or line['tax_ids']):
                # SI NO ES LINEA DE IMPUESTO O ES LINEA SIN IMPUESTOS CORRESPONDE A NO GRAVADO
                lines[key]['no_taxed'] += amount

        return lines, c_taxes, retention_perception_summary

    def _get_lines(self, cols, vat_cols):  # noqa: C901
        lines, c_taxes, retention_perception_summary = self._group_lines_data(
            cols, vat_cols
        )
        fiscal_credit_name = {
            'direct_taxed': 'Directo Gravado',
            'direct_exempt': 'Directo Exento',
            'apport': 'Prorrateable',
        }
        unassigned_fiscal_credit_name = _('Sin clasificar')

        # FIX: se usan defaultdict en vez de diccionarios con solo
        # '10.5%'/'21.0%'/'27.0%' precargadas. El sistema tiene tambien
        # tasas de IVA al 2.5% y al 5% (ver account.tax-ar_eynes.csv), y
        # con un dict fijo cualquier linea con esas alicuotas y
        # fiscal_credit clasificado hacia explotar con KeyError. El
        # bloque "TOTALES POR ALICUOTA" del qweb solo tiene columnas para
        # 10.5/21/27, asi que estas otras alicuotas no se ven ahi todavia
        # (si se agregan columnas nuevas hay que tocar el reporte de
        # l10n_ar_eynes), pero ya no rompen la impresion del reporte.
        by_fiscal_credit = {
            # TIENEN RELACIONADO IVA PERO TIENEN FISCAL_CREDIT = direct_taxed, apport, direct_exempt
            'direct_taxed': defaultdict(lambda: [0.0, 0.0]),
            'apport': defaultdict(lambda: [0.0, 0.0]),
            'direct_exempt': defaultdict(lambda: [0.0, 0.0]),
            'direct_taxed_refund': defaultdict(lambda: [0.0, 0.0]),
            'apport_refund': defaultdict(lambda: [0.0, 0.0]),
            'direct_exempt_refund': defaultdict(lambda: [0.0, 0.0]),
            # TIENEN RELACIONADO IVA EXENTO
            'Exento': 0.0,
            'Exento_refund': 0.0,
            # NO TIENEN RELACIONADO IVA
            'untaxed': 0.0,
            'untaxed_refund': 0.0,
            # NO TIENEN RELACIONADO IVA Y ADEMAS NO SON RESPONSABLES INSCRIPTOS
            'ni_nr_ex_mon': 0.0,
            'ni_nr_ex_mon_refund': 0.0,
        }
        new_lines = []
        totals = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        totals_fc_nd = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        totals_nc = [0] * (
            len(cols) + 4
        )  # +4 for base_vat, vat, no_taxed and total
        for line in lines.values():
            new_line = (
                [
                    line['date'],
                    line['partner_name'][:20],
                    line['partner_vat'],
                    line['invoice_type'],
                    line['invoice_number'],
                    line['no_taxed'],
                ]
                + line['taxes']
                + [
                    line['total'],
                ]
            )

            first_vat = True
            for vat_values in line['vat_taxes'].values():
                vat_split = list(vat_values.keys())
                vat_split.remove('name')
                # FIX: 'is_exempt' no es un valor de fiscal_credit, se
                # separa para no iterarlo como si fuera uno.
                if 'is_exempt' in vat_split:
                    vat_split.remove('is_exempt')

                # FIX: un impuesto es "0% IVA" tanto si esta marcado
                # is_exempt=True (p.ej. "IVA Exento") como si su alicuota
                # numerica es 0 (p.ej. "IVA 0.00%"). En ambos casos no
                # existe credito fiscal real para prorratear.
                is_zero_rate = vat_values.get('is_exempt', False)
                if not is_zero_rate:
                    vat_aliquot_name = vat_values['name']
                    try:
                        is_zero_rate = (
                            float(vat_aliquot_name.replace('%', '')) == 0
                        )
                    except ValueError:
                        is_zero_rate = False

                for raw_fiscal_credit in vat_split:
                    if not first_vat:
                        new_line = [''] * 5
                        new_line = new_line + (
                            [0] * (len(cols) + 2)
                        )  # +2 for no_taxed and total
                    base_vat_amount = vat_values[raw_fiscal_credit]
                    vat_aliquot = vat_values['name']
                    try:
                        vat_amount = round(
                            base_vat_amount
                            * (float(vat_aliquot.replace('%', '')) / 100),
                            2,
                        )
                    except ValueError:
                        vat_amount = 0.0

                    # FIX: si no hay fiscal_credit clasificado pero el IVA
                    # es 0%, se asume 'direct_exempt' en vez de descartar
                    # la linea del desglose del reporte.
                    fiscal_credit = raw_fiscal_credit
                    if not fiscal_credit and is_zero_rate:
                        fiscal_credit = 'direct_exempt'

                    new_line.insert(5, base_vat_amount)
                    new_line.insert(6, vat_aliquot)
                    new_line.insert(7, vat_amount)
                    new_line.insert(
                        8,
                        fiscal_credit_name.get(
                            fiscal_credit, unassigned_fiscal_credit_name
                        ),
                    )
                    new_lines.append(new_line)
                    first_vat = False

                    totals[0] += base_vat_amount
                    totals[1] += vat_amount
                    if fiscal_credit not in fiscal_credit_name:
                        _logger.warning(
                            "Skipping apportionable VAT fiscal credit summary "
                            "for invoice %s (%s): unexpected fiscal_credit=%r",
                            line['invoice_number'],
                            line['invoice_type'],
                            raw_fiscal_credit,
                        )
                        continue
                    is_refund = line['invoice_type'].startswith('NC')
                    if is_refund:
                        totals_nc[0] += base_vat_amount
                        totals_nc[1] += vat_amount
                        fiscal_credit = fiscal_credit + '_refund'
                    else:
                        totals_fc_nd[0] += base_vat_amount
                        totals_fc_nd[1] += vat_amount

                    # FIX: se clasifica por is_zero_rate (flag/alicuota real)
                    # en vez de comparar el nombre limpio contra 'Exento', y
                    # se separa correctamente Exento de Exento_refund segun
                    # si la linea es una Nota de Credito.
                    if is_zero_rate:
                        exempt_key = 'Exento_refund' if is_refund else 'Exento'
                        by_fiscal_credit[exempt_key] += base_vat_amount
                    else:
                        if vat_aliquot not in ('10.5%', '21.0%', '27.0%'):
                            _logger.warning(
                                "Apportionable VAT aliquot %r for invoice "
                                "%s (%s) has no dedicated column in the "
                                "report template; amount is included in "
                                "general totals but not in the per-rate "
                                "breakdown.",
                                vat_aliquot,
                                line['invoice_number'],
                                line['invoice_type'],
                            )
                        by_fiscal_credit[fiscal_credit][vat_aliquot][
                            0
                        ] += base_vat_amount
                        by_fiscal_credit[fiscal_credit][vat_aliquot][
                            1
                        ] += vat_amount

            by_fiscal_credit_untaxed_key = 'untaxed'
            if first_vat:
                # If this value is True, it is a no taxed invoice (maybe C type)
                new_line.insert(5, 0.0)
                new_line.insert(6, '')
                new_line.insert(7, 0.0)
                new_line.insert(8, '')
                new_lines.append(new_line)
                by_fiscal_credit_untaxed_key = 'ni_nr_ex_mon'

            for i, amount in enumerate(line['taxes']):
                i = (
                    i + 3
                )  # +3 for base_vat_amount, vat_amount and no_taxed_amount
                totals[i] += amount
                if line['invoice_type'].startswith('NC'):
                    totals_nc[i] += amount
                else:
                    totals_fc_nd[i] += amount

            totals[2] += line['no_taxed']
            totals[-1] += line['total']
            if line['invoice_type'].startswith('NC'):
                totals_nc[2] += line['no_taxed']
                totals_nc[-1] += line['total']
                by_fiscal_credit_untaxed_key = (
                    by_fiscal_credit_untaxed_key + '_refund'
                )
            else:
                totals_fc_nd[2] += line['no_taxed']
                totals_fc_nd[-1] += line['total']

            by_fiscal_credit[by_fiscal_credit_untaxed_key] += line['no_taxed']

        totals.insert(1, '')
        totals.insert(3, '')
        totals_nc.insert(1, '')
        totals_nc.insert(3, '')
        totals_fc_nd.insert(1, '')
        totals_fc_nd.insert(3, '')

        new_retention_perception_summary = []
        for line in retention_perception_summary.values():
            new_retention_perception_summary.append(
                [
                    line[0].get('es_AR', line[0].get('en_US', '')),
                    line[1],
                ]
            )

        for fiscal_type in (
            'direct_taxed',
            'apport',
            'direct_exempt',
            'direct_taxed_refund',
            'apport_refund',
            'direct_exempt_refund',
        ):
            aliquots = (
                by_fiscal_credit[fiscal_type]['10.5%'],
                by_fiscal_credit[fiscal_type]['21.0%'],
                by_fiscal_credit[fiscal_type]['27.0%'],
            )
            by_fiscal_credit[fiscal_type] = aliquots

        return (
            new_lines,
            totals,
            totals_fc_nd,
            totals_nc,
            c_taxes,
            new_retention_perception_summary,
            by_fiscal_credit,
        )
