import csv
import tempfile
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import ValidationError

from odoo.tests import TransactionCase, tagged
from ..csv_source import FILES, HEADERS, load
from ..models.csv_import_run import CONTEXT


@tagged('post_install', '-at_install')
class TestCsvImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['res.partner.csv.import.run']
        cls.partners = cls.env['res.partner'].with_company(cls.env['res.company'].browse(1)).with_context(**CONTEXT)

    def row(self, code='CSV-TEST-001', **overrides):
        data = dict.fromkeys(HEADERS, '')
        data.update({'Nombre': 'CSV test partner', 'Código de Cliente': code,
                     'Código Bejerman': code, 'Empresa': 'El Jumillano S.A.',
                     'Tipo de empresa': 'EMPRESA', 'País': 'ARGENTINA',
                     'Es Cliente': 'TRUE', 'Es Proveedor': 'FALSE'})
        data.update(overrides)
        return dict(file=FILES[2], row=2, raw=data.copy(), data=data, company=1,
                    key=code, error='', parent_key='', parent_company=None, parent_row=None)

    def test_create_update_idempotent_and_supplier(self):
        lookups = self.service._lookups()
        row = self.row()
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'created')
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'unchanged')
        row['data']['Nombre'] = 'Changed'
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'updated')
        record = self.partners.search([('codigo_bejerman', '=', row['key'])])
        record.write({'supplier_rank': 1, 'email': 'csv-test@example.invalid'})
        row['data']['Nombre'] = 'Do not overwrite'
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'supplier_protected')
        self.assertEqual(record.name, 'Changed')

    def test_company_child_inherits_commercial(self):
        lookups = self.service._lookups()
        mother = self.row('CSV-MOTHER', Calle='Mother Street 1')
        child = self.row('CSV-CHILD', Calle='Child Street 2')
        child['parent_key'] = mother['key']
        child['parent_company'] = mother['company']
        self.service._apply_row(mother, lookups)
        self.service._apply_row(child, lookups)
        record = self.partners.search([('codigo_bejerman', '=', child['key'])])
        self.assertEqual(record.street, 'Child Street 2')
        self.assertEqual(record.parent_id.street, 'Mother Street 1')
        self.assertEqual(record.type, 'other')
        self.assertTrue(record.is_company)
        self.assertTrue(record.csv_inherit_commercial)
        self.assertEqual(record.commercial_partner_id, record.parent_id)
        record.write({'name': 'Still a company'})
        self.assertEqual(record.commercial_partner_id, record.parent_id)

    def test_bad_relation_and_savepoint(self):
        row = self.row(**{'Tipo de cliente': 'DOES NOT EXIST CSV TEST'})
        with self.assertRaisesRegex(ValueError, 'relation_missing'):
            with self.env.cr.savepoint():
                self.service._apply_row(row, self.service._lookups())
        self.assertFalse(self.partners.search([('codigo_bejerman', '=', row['key'])]))

    def test_preflight_rejects_child_across_companies(self):
        # A mother tagged with a different Empresa than her child in the
        # source CSV is not a valid link: verified explicitly and rejected
        # as missing_or_rejected_mother, not silently accepted.
        with tempfile.TemporaryDirectory() as directory:
            for filename in FILES:
                with (Path(directory) / filename).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
                    writer.writeheader()
                    if filename == FILES[2]:
                        mother = self.row('XCO-MOTHER')
                        mother['data']['Empresa'] = 'Lufran S.A.'
                        writer.writerow(mother['data'])
                        writer.writerow(self.row('XCO-CHILD', nrosub='XCO-MOTHER')['data'])
            rows, summary = load(directory)
            self.assertEqual(summary['rejected']['missing_or_rejected_mother'], 1)
            child = next(r for r in rows if r['data']['Código de Cliente'] == 'XCO-CHILD')
            self.assertEqual(child['error'], 'missing_or_rejected_mother')
            self.assertEqual(child['parent_key'], '')
            self.assertIsNone(child['parent_company'])
            self.assertIsNone(child['parent_row'])

    def test_children_never_carry_a_bejerman_code(self):
        # Código Bejerman only identifies the mother: every child is left
        # with an empty code, regardless of what her own CSV row carries in
        # that column, and never collides with a sibling under the same
        # (company, key) even though all children now share the empty key.
        with tempfile.TemporaryDirectory() as directory:
            for filename in FILES:
                with (Path(directory) / filename).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
                    writer.writeheader()
                    if filename == FILES[2]:
                        mother = self.row('MOTHER-BEJ', **{'Código de Cliente': 'MOM-CODE'})
                        child = self.row('SHARED-BEJ', **{
                            'Código de Cliente': 'CHILD-CODE', 'nrosub': 'MOM-CODE'})
                        other_child = self.row('OWN-BEJ', **{
                            'Código de Cliente': 'OTHER-CHILD-CODE', 'nrosub': 'MOM-CODE'})
                        writer.writerow(mother['data'])
                        writer.writerow(child['data'])
                        writer.writerow(other_child['data'])
            rows, summary = load(directory)
            self.assertNotIn('duplicate_key', summary['rejected'])
            self.assertNotIn('missing_or_rejected_mother', summary['rejected'])
            mother_row = next(r for r in rows if r['data']['Código de Cliente'] == 'MOM-CODE')
            child_row = next(r for r in rows if r['data']['Código de Cliente'] == 'CHILD-CODE')
            other_row = next(r for r in rows if r['data']['Código de Cliente'] == 'OTHER-CHILD-CODE')
            self.assertEqual(mother_row['key'], 'MOTHER-BEJ')
            self.assertEqual(child_row['key'], '')
            self.assertEqual(other_row['key'], '')
            self.assertEqual(child_row['parent_key'], mother_row['key'])
            self.assertEqual(other_row['parent_key'], mother_row['key'])

    def test_child_with_empty_key_is_identified_by_customer_code(self):
        lookups = self.service._lookups()
        mother = self.row('CSV-BLANK-MOTHER', Calle='Mother Street 1')
        child = self.row('CSV-BLANK-CHILD', **{'Código Bejerman': ''}, Calle='Child Street 2')
        child['key'] = ''
        child['parent_key'] = mother['key']
        child['parent_company'] = mother['company']
        self.service._apply_row(mother, lookups)
        self.assertEqual(self.service._apply_row(child, lookups)[0], 'created')
        record = self.partners.search([('customer_code', '=', 'CSV-BLANK-CHILD')])
        self.assertFalse(record.codigo_bejerman)
        self.assertEqual(record.parent_id.codigo_bejerman, mother['key'])
        # Idempotent: found again by customer_code, not by the (blank) code.
        self.assertEqual(self.service._apply_row(child, lookups)[0], 'unchanged')
        child['data']['Calle'] = 'Child Street 2 updated'
        self.assertEqual(self.service._apply_row(child, lookups)[0], 'updated')
        self.assertEqual(record.street, 'Child Street 2 updated')

    def test_duplicates_orphan_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename in FILES:
                with (Path(directory) / filename).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
                    writer.writeheader()
                    if filename == FILES[2]:
                        writer.writerow(self.row('CHILD', nrosub='MOTHER')['data'])
                        writer.writerow(self.row('MOTHER')['data'])
                        writer.writerow(self.row('DUP')['data'])
                        writer.writerow(self.row('DUP')['data'])
                        writer.writerow(self.row('ORPHAN', nrosub='MISSING')['data'])
            rows, summary = load(directory)
            self.assertEqual(summary['total'], 5)
            self.assertEqual(summary['rejected']['duplicate_key'], 2)
            self.assertEqual(summary['rejected']['missing_or_rejected_mother'], 1)
            self.assertLess(next(i for i, r in enumerate(rows) if r['data']['Código de Cliente'] == 'MOTHER'),
                            next(i for i, r in enumerate(rows) if r['data']['Código de Cliente'] == 'CHILD'))

    def test_shared_identity_rejected(self):
        row = self.row()
        self.partners.create({'name': 'Shared', 'codigo_bejerman': row['key'], 'company_id': False})
        with self.assertRaisesRegex(ValueError, 'shared_partner'):
            self.service._apply_row(row, self.service._lookups())

    def test_no_external_padron(self):
        # The import-specific method must return before invoking the padron stack.
        self.assertFalse(self.partners.do_update_from_padron())

    def test_archived_supplier_and_family_are_protected(self):
        lookups = self.service._lookups()
        mother = self.row('CSV-PROTECTED-MOTHER')
        self.service._apply_row(mother, lookups)
        partner = self.partners.search([('codigo_bejerman', '=', mother['key'])])
        supplier = self.partners.create({'name': 'Supplier child', 'parent_id': partner.id,
                                        'company_id': 1, 'is_company': True,
                                        'type': 'other', 'supplier_rank': 1,
                                        'email': 'supplier@example.invalid', 'active': False})
        mother['data']['Nombre'] = 'Must not change'
        with self.assertRaisesRegex(ValueError, 'supplier_in_commercial_family'):
            self.service._apply_row(mother, lookups)
        self.assertEqual(partner.name, 'CSV test partner')
        row = self.row('CSV-SUPPLIER-ARCHIVED')
        supplier.write({'codigo_bejerman': row['key']})
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'supplier_protected')

    def test_company_scoped_identity(self):
        lookups = self.service._lookups()
        first = self.row('CSV-MULTICOMPANY')
        second = self.row('CSV-MULTICOMPANY')
        second['company'] = 8
        second['data']['Empresa'] = 'Lufran S.A.'
        self.service._apply_row(first, lookups)
        self.service._apply_row(second, lookups)
        records = self.partners.search([('codigo_bejerman', '=', first['key'])])
        self.assertEqual(set(records.mapped('company_id').ids), {1, 8})
        self.assertEqual(len(records), 2)

    def test_confirmed_payment_aliases(self):
        lookups = self.service._lookups()
        row = self.row(**{'Términos de pago del cliente': 'CONTADO'})
        values, _ = self.service._values(row, lookups)
        self.assertEqual(values['property_payment_term_id'], 1)
        row['data']['Términos de pago del cliente'] = 'CTA. CORRIENTE'
        values, _ = self.service._values(row, lookups)
        self.assertEqual(values['property_payment_term_id'], 25)

    def test_savepoint_rolls_back_a_partially_written_row(self):
        row = self.row('CSV-ROLLBACK')
        model = type(self.partners)
        original = model.create
        def failing_create(records, values):
            original(records, values)
            raise ValidationError('simulated constraint after create')
        with patch.object(model, 'create', failing_create):
            with self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.service._apply_row(row, self.service._lookups())
        self.assertFalse(self.partners.search([('codigo_bejerman', '=', row['key'])]))

    def test_company_default_pricelist_ignores_csv_and_updates_existing(self):
        lookups = self.service._lookups()
        for company in (1, 8):
            row = self.row(f'CSV-DEFAULT-{company}', ListaPrecio='MISSING CSV LIST')
            row['company'] = company
            expected = lookups[company, 'default_pricelist']
            self.service._apply_row(row, lookups)
            record = self.partners.with_company(self.env['res.company'].browse(company)).search([
                ('codigo_bejerman', '=', row['key']), ('company_id', '=', company)])
            self.assertEqual(record.property_product_pricelist.id, expected)
            self.assertEqual(record.property_product_pricelist.company_id.id, company)
            alternative = self.env['product.pricelist'].with_company(record.company_id).create({
                'name': 'Alternative for test', 'company_id': company, 'sequence': 999})
            record.write({'property_product_pricelist': alternative.id})
            self.assertEqual(self.service._apply_row(row, lookups)[0], 'updated')
            self.assertEqual(record.property_product_pricelist.id, expected)
            self.assertEqual(self.service._apply_row(row, lookups)[0], 'unchanged')

    def test_other_companies_are_not_destinations(self):
        for company in (5, 9):
            row = self.row()
            row['company'] = company
            with self.assertRaisesRegex(ValueError, 'invalid_destination_company'):
                self.service._values(row, self.service._lookups())

    def test_company_name_accepts_accent_but_requires_sa(self):
        from ..csv_source import COMPANIES, normalize
        def resolve(name):
            return next((cid for label, cid in COMPANIES.items()
                         if normalize(label) == normalize(name)), None)
        self.assertEqual(resolve('Lufrán S.A.'), 8)
        self.assertEqual(resolve('Lufran S.A.'), 8)
        self.assertIsNone(resolve('Lufrán'))
        self.assertIsNone(resolve('El Jumillano'))

    def test_coordinate_precision_does_not_cause_repeated_updates(self):
        row = self.row('CSV-GEO', **{'Geo latitud': '-34.63540540053784',
                                    'Geo longitud': '-58.532608636328135'})
        lookups = self.service._lookups()
        self.service._apply_row(row, lookups)
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(self.service._apply_row(row, lookups)[0], 'unchanged')

    def test_invalid_phones_are_preserved_on_create_update_and_replay(self):
        lookups = self.service._lookups()
        values = ['1121806628PAULA', '1.13772756615377E+19', '0345154964349 apoder']
        for index, value in enumerate(values):
            row = self.row(f'CSV-RAW-PHONE-{index}', **{
                'Teléfono': value, 'Numero de Celular': value})
            status, warnings = self.service._apply_row(row, lookups)
            self.assertEqual(status, 'created')
            self.assertIn('phone_format_preserved:Teléfono', warnings)
            self.assertIn('phone_format_preserved:Numero de Celular', warnings)
            record = self.partners.search([('codigo_bejerman', '=', row['key'])])
            self.env.flush_all()
            self.env.invalidate_all()
            self.assertEqual(record.phone, value)
            self.assertEqual(record.mobile_number, value)
            self.assertEqual(self.service._apply_row(row, lookups)[0], 'unchanged')
            row['data']['Teléfono'] = value + ' texto adicional'
            self.assertEqual(self.service._apply_row(row, lookups)[0], 'updated')
            self.assertEqual(record.phone, row['data']['Teléfono'])

    def test_per_file_sample_preserves_global_errors_and_mothers(self):
        from ..csv_source import select_rows
        with tempfile.TemporaryDirectory() as directory:
            for filename in FILES:
                with (Path(directory) / filename).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
                    writer.writeheader()
                    if filename == FILES[2]:
                        for data in [self.row('CHILD', nrosub='MOTHER')['data'],
                                     self.row('FILLER')['data'], self.row('MOTHER')['data'],
                                     self.row('LATER')['data']]:
                            writer.writerow(data)
                    else:
                        for code in ('DUP', 'SECOND', 'THIRD', 'DUP'):
                            row = self.row(filename + code)['data']
                            if filename == FILES[1]:
                                row['Empresa'] = 'Lufrán S.A.'
                            writer.writerow(row)
            rows, summary = load(directory)
            selected, sample = select_rows(rows, summary, 2)
            self.assertEqual(sample['total'], 6)
            self.assertEqual(sample['files'], dict.fromkeys(FILES, 2))
            self.assertEqual(sample['rejected'], {'duplicate_key': 2})
            hierarchy = [r for r in selected if r['file'] == FILES[2]]
            self.assertEqual([r['key'] for r in hierarchy], ['MOTHER', ''])
            self.assertEqual([r['row'] for r in hierarchy], [4, 2])
            self.assertNotEqual(sample['fingerprint'], summary['fingerprint'])
            self.assertNotEqual(sample['fingerprint'], select_rows(rows, summary, 3)[1]['fingerprint'])
            self.assertEqual(sample, select_rows(rows, summary, 2)[1])
            self.assertEqual(select_rows(rows, summary, 0), (rows, summary))
            with self.assertRaisesRegex(ValueError, 'fewer than'):
                select_rows(rows, summary, 5)
