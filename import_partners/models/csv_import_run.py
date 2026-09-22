"""Shell-only ORM importer. Checkpoint, reports and partners commit atomically."""
import base64
import csv
import io
import logging
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

from psycopg2 import IntegrityError
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

from ..csv_source import COMPANIES, HEADERS, load, normalize, select_rows

_logger = logging.getLogger(__name__)
LOCK = 1947031926
CONTEXT = dict(tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
               mail_create_nosubscribe=True, mail_notify_force_send=False,
               ivess_csv_import=True, skip_multicompany_fiscal_position=True,
               skip_multicompany_fiscal_position_propagation=True, active_test=False)
SIMPLE = {'Nombre': 'name', 'Correo electronico': 'email', 'Calle': 'street',
          'Ciudad': 'city', 'Código de Cliente': 'customer_code'}
BOOLEANS = {'Es Cliente': 'is_customer', 'Es Proveedor': 'is_supplier',
            'Cliente Importante': 'is_important_client',
            'Precios Especiales': 'has_special_price',
            'Requiere Comprobante': 'requiere_comprobante'}
RELATIONS = {'Estado': ('res.country.state', 'name', 'state_id'),
             'Tipo de Documento': ('res.document.type', 'name', 'document_type_id'),
             'Posición fiscal': ('account.fiscal.position', 'name', 'property_account_position_id'),
             'Tipo de cliente': ('client.type', 'description', 'partner_type_id'),
             'Etiqueta': ('res.partner.category', 'name', 'category_id'),
             'Términos de pago del cliente': ('account.payment.term', 'name', 'property_payment_term_id')}


def boolean(value):
    if value.upper() in ('TRUE', '1'):
        return True
    if value.upper() in ('FALSE', '0', ''):
        return False
    raise ValueError('invalid_boolean: ' + value)


def phone(value, warnings, column):
    """Preserve source text; questionable phone formats never reject a row."""
    if not value:
        return False
    if not re.fullmatch(r'[\d\s+()./\-]+', value):
        warnings.append('phone_format_preserved:' + column)
    return value


class CsvImportRun(models.Model):
    _name = 'res.partner.csv.import.run'
    _description = 'Ejecución importación CSV de partners'
    _order = 'id desc'

    name = fields.Char(required=True)
    fingerprint = fields.Char(required=True, readonly=True)
    checkpoint = fields.Integer(readonly=True)
    total = fields.Integer(readonly=True)
    rejected_mothers = fields.Json(readonly=True, default=list)
    file_counts = fields.Json(readonly=True, default=dict)
    counts = fields.Json(readonly=True, default=dict)
    state = fields.Selection([('running', 'En curso'), ('done', 'Finalizada')], default='running')

    @api.model
    def _csv_dir(self):
        """Where the upload wizard writes the CSVs, and where the shell
        scripts read them from by default (no SFTP/SSH file transfer
        needed). Scoped by database name to keep multiple DBs on the same
        server from overwriting each other's files."""
        path = os.path.join(config['data_dir'], 'csv_import', self.env.cr.dbname)
        os.makedirs(path, exist_ok=True)
        return path

    @api.model
    def _lookups(self):
        result = {}
        for company_name, company_id in COMPANIES.items():
            company = self.env['res.company'].browse(company_id).exists()
            if not company or normalize(company.name) != normalize(company_name):
                raise UserError(f'Company {company_id} must be {company_name}')
            argentina = self.env.ref('base.ar')
            pricelists = self.env['product.pricelist'].with_company(company).with_context(
                allowed_company_ids=[company_id], active_test=True, country_code=False)
            default = pricelists._get_country_pricelist_multi([argentina.id])[argentina.id].exists()
            if len(default) != 1 or not default.active or default.company_id != company:
                raise UserError(f'No active default pricelist belonging to {company_name}')
            result[company_id, 'default_pricelist'] = default.id
            for column, (model, label, destination) in RELATIONS.items():
                obj = self.env[model].with_company(company).with_context(lang='es_AR')
                domain = [('company_id', 'in', [False, company_id])] if 'company_id' in obj._fields else []
                if model == 'res.country.state':
                    domain += [('country_id.code', '=', 'AR')]
                names = defaultdict(list)
                for record in obj.search(domain):
                    names[normalize(record[label])].append(record.id)
                if column == 'Términos de pago del cliente':
                    for source, target in {'CONTADO': 'Pago inmediato - Contado',
                                           'CTA. CORRIENTE': 'CTA CTE'}.items():
                        names[normalize(source)] = names.get(normalize(target), [])
                result[company_id, column] = names
        return result

    @api.model
    def _values(self, row, lookups):
        data, company = row['data'], row['company']
        warnings = []
        if company not in COMPANIES.values():
            raise ValueError('invalid_destination_company')
        if normalize(data['País']) != 'argentina':
            raise ValueError('invalid_country')
        vals = {field: data[column] or False for column, field in SIMPLE.items()}
        vals.update({field: boolean(data[column]) for column, field in BOOLEANS.items()})
        if data['Tipo de empresa'] not in ('EMPRESA', 'PERSONA'):
            raise ValueError('invalid_company_type')
        vals.update(company_id=company, codigo_bejerman=row['key'] or False,
                    company_type='company' if data['Tipo de empresa'] == 'EMPRESA' else 'person',
                    country_id=self.env.ref('base.ar').id,
                    phone=phone(data['Teléfono'], warnings, 'Teléfono'),
                    mobile_number=phone(data['Numero de Celular'], warnings, 'Numero de Celular'))
        for column, (_, _, field) in RELATIONS.items():
            value = data[column]
            matches = lookups[company, column].get(normalize(value), []) if value else []
            if value and len(matches) != 1:
                raise ValueError(f'relation_missing_or_ambiguous: {column}={value}')
            vals[field] = matches[0] if matches else False
        vals['property_product_pricelist'] = lookups[company, 'default_pricelist']
        vals['category_id'] = [(6, 0, [vals['category_id']] if vals['category_id'] else [])]
        if vals['is_supplier'] and not vals['email']:
            vals['is_supplier'] = False
            warnings.append('supplier_without_email')
        vat = re.sub(r'[.\-\s]', '', data['NrCUIT'])
        wizard = self.env['res.partner.import.wizard']
        valid = vat and vat != '0' and vals['document_type_id'] and wizard._check_vat_ar(
            vat, vals['document_type_id'], self.env.ref('l10n_ar_eynes.document_cuit').id,
            self.env.ref('l10n_ar_eynes.document_cuil').id, self.env.ref('l10n_ar_eynes.document_dni').id)
        if not valid:
            vals['document_type_id'] = self.env.ref('l10n_ar_eynes.document_doc_otro').id
            vat = 'NOIMPORTADO'
            warnings.append('document_fallback')
        vals['vat'] = vat
        vals['fecha_alta'] = datetime.fromisoformat(data['Fecha de Alta']).replace(microsecond=0) if data['Fecha de Alta'] else False
        for column, field, bound in [('Geo latitud', 'partner_latitude', 90), ('Geo longitud', 'partner_longitude', 180)]:
            value = data[column]
            coord = float(value.replace(',', '.')) if value else 0.0
            # These CSVs already contain decimal points. Never invent precision.
            if not math.isfinite(coord) or abs(coord) > bound:
                raise ValueError('invalid_coordinate: ' + column)
            vals[field] = coord
        hour = data['Horario promedio']
        vals['average_hour'] = 0.0
        if hour:
            parsed = datetime.strptime(hour, '%H:%M')
            vals['average_hour'] = parsed.hour + parsed.minute / 60
        return vals, warnings

    @api.model
    def _apply_row(self, row, lookups):
        if row['error']:
            raise ValueError(row['error'])
        company = self.env['res.company'].browse(row['company'])
        partners = self.env['res.partner'].with_company(company).with_context(**CONTEXT)
        if row['parent_key']:
            # A child never carries her own codigo_bejerman (see _values):
            # identify and update her by Código de Cliente instead.
            existing = partners.search([('customer_code', '=', row['data']['Código de Cliente']),
                                        ('company_id', 'in', [False, company.id])])
        else:
            existing = partners.search([('codigo_bejerman', '=', row['key']),
                                        ('company_id', 'in', [False, company.id])])
        if len(existing) > 1 or (existing and not existing.company_id):
            raise ValueError('ambiguous_or_shared_partner')
        if existing and (existing.is_supplier or existing.supplier_rank > 0):
            return 'supplier_protected', []
        # A changed Bejerman must not silently duplicate an existing customer.
        other = partners.search([('customer_code', '=', row['data']['Código de Cliente']),
                                 ('company_id', 'in', [False, company.id]), ('id', 'not in', existing.ids)], limit=1)
        if other:
            raise ValueError('customer_code_conflict')
        parent = partners.browse()
        if row['parent_key']:
            parent = partners.search([('codigo_bejerman', '=', row['parent_key']), ('company_id', '=', company.id)])
            if len(parent) != 1:
                raise ValueError('mother_not_imported')
        # ORM commercial/address synchronization may touch relatives, too.
        roots = (existing | parent).mapped('commercial_partner_id')
        if roots and partners.search_count([('id', 'child_of', roots.ids),
                                           '|', ('is_supplier', '=', True), ('supplier_rank', '>', 0)]):
            raise ValueError('supplier_in_commercial_family')
        if existing.parent_id and not row['file'].startswith('page_ctas_'):
            raise ValueError('unexpected_existing_parent')
        vals, warnings = self._values(row, lookups)
        if row['file'].startswith('page_ctas_'):
            vals.update(parent_id=parent.id or False, csv_inherit_commercial=bool(parent))
            if parent:
                vals['type'] = 'other'
                # Commercial fields belong to the mother. Do not let a child
                # overwrite her VAT or pricelist through Odoo synchronization.
                inherited = parent._convert_fields_to_values(parent._commercial_fields())
                # Mother has already been assigned the same company default.
                if parent.property_product_pricelist.id != vals['property_product_pricelist']:
                    raise ValueError('mother_pricelist_not_company_default')
                for key in vals.keys() & inherited.keys():
                    if vals[key] != inherited[key]:
                        warnings.append('inherited_from_mother:' + key)
                    vals[key] = inherited[key]
        if existing:
            # Avoid writing unchanged records, including their write_date.
            changes = {}
            for key, value in vals.items():
                field = existing._fields[key]
                current = existing[key]
                if field.type == 'float':
                    value = field.convert_to_cache(value, existing)
                if key == 'property_product_pricelist' and not value:
                    current = existing.specific_property_product_pricelist
                equal = current.id == value if field.type == 'many2one' else (
                    set(current.ids) == set(value[0][2]) if field.type == 'many2many' else current == value)
                if not equal:
                    changes[key] = value
            if not changes:
                return 'unchanged', warnings
            existing.write(changes)
            return 'updated', warnings
        partners.create(vals)
        return 'created', warnings

    @api.model
    def _report(self, run, start, records):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['file', 'row', 'status', 'reason', *HEADERS])
        for row, status, reason in records:
            # Prevent formula execution when opened as a spreadsheet.
            values = [row['file'], row['row'], status, reason, *[row['raw'][h] for h in HEADERS]]
            writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
        payload = stream.getvalue().encode('utf-8-sig')
        self.env['ir.attachment'].create(dict(
            name=f'partner-import-{run.id}-{start:09d}.csv', type='binary',
            datas=base64.b64encode(payload), mimetype='text/csv',
            res_model=self._name, res_id=run.id))

    @api.model
    def _run(self, directory, *, expected_db, dry_run=True, batch_size=500,
             limit=0, run_id=None, per_file_limit=0, exclude=frozenset()):
        """Private shell API: owns transaction. Never call from HTTP or a cron.

        dry_run executes the actual ORM and rolls everything back, including
        reports and checkpoint. Its returned issues can be exported locally.
        limit is the maximum number of additional rows, not a dataset prefix.
        per_file_limit fixes the dataset quota for each source before batching;
        0 imports all rows. The quota is part of the resumable fingerprint.
        exclude: (filename, row) pairs an operator decided to skip upfront
        (e.g. a known source-data duplicate); part of the resumable fingerprint.
        """
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise UserError('Administrator required')
        if self.env.cr.dbname != expected_db:
            raise UserError('Database does not match expected_db')
        if batch_size < 1 or limit < 0 or per_file_limit < 0 or (dry_run and run_id):
            raise UserError('Invalid batch_size, limit or dry-run resume')
        self.env.cr.execute('SELECT pg_try_advisory_lock(%s)', [LOCK])
        if not self.env.cr.fetchone()[0]:
            raise UserError('Another partner import is running')
        dry_issues = []
        try:
            rows, summary = select_rows(*load(directory, exclude=exclude), per_file_limit=per_file_limit)
            lookups = self._lookups()
            run = self.browse(run_id).exists() if run_id else self.create(dict(
                name=summary['fingerprint'][:16], fingerprint=summary['fingerprint'], total=len(rows)))
            if not run or run.fingerprint != summary['fingerprint']:
                raise UserError('Missing run or changed input/version; cannot resume')
            start = run.checkpoint
            end = min(len(rows), start + limit) if limit else len(rows)
            counts = Counter(run.counts or {})
            file_counts = {filename: Counter((run.file_counts or {}).get(filename, {}))
                           for filename in summary['files']}
            rejected_mothers = set(run.rejected_mothers or [])
            for offset in range(start, end, batch_size):
                records = []
                stop = min(offset + batch_size, end)
                for row in rows[offset:stop]:
                    try:
                        with self.env.cr.savepoint():
                            if f"{row['company']}:{row['parent_key']}" in rejected_mothers:
                                raise ValueError('mother_rejected_in_run')
                            status, warnings = self._apply_row(row, lookups)
                        counts[status] += 1
                        file_counts[row['file']][status] += 1
                        if status == 'supplier_protected' or warnings:
                            records.append((row, status, ','.join(warnings) or status))
                    except (ValueError, ValidationError, UserError, IntegrityError) as error:
                        if row['file'].startswith('page_ctas_') and not row['data']['nrosub']:
                            rejected_mothers.add(f"{row['company']}:{row['key']}")
                        counts['rejected'] += 1
                        file_counts[row['file']]['rejected'] += 1
                        records.append((row, 'rejected', str(error)))
                self._report(run, offset, records)
                run.write(dict(checkpoint=stop, counts=dict(counts),
                               file_counts={f: dict(c) for f, c in file_counts.items()}, rejected_mothers=sorted(rejected_mothers), state='done' if stop == len(rows) else 'running'))
                if dry_run:
                    dry_issues.extend(dict(file=r['file'], row=r['row'], status=s, reason=e) for r, s, e in records)
                else:
                    self.env.cr.commit()
                    self.env.invalidate_all()
                _logger.info('CSV import run=%s dry=%s progress=%s/%s counts=%s', run.id, dry_run, stop, len(rows), dict(counts))
            if start == end:
                run.write({'state': 'done' if end == len(rows) else 'running'})
                if not dry_run:
                    self.env.cr.commit()
            result = dict(run_id=run.id if not dry_run else None, dry_run=dry_run,
                          checkpoint=end, total=len(rows), counts=dict(counts), preflight=summary,
                          file_counts={f: dict(c) for f, c in file_counts.items()},
                          issues=dry_issues)
            if dry_run:
                self.env.cr.rollback()
            return result
        except BaseException:
            self.env.cr.rollback()
            raise
        finally:
            self.env.cr.execute('SELECT pg_advisory_unlock(%s)', [LOCK])
