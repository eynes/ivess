"""1000 rows per source, dry-run/apply/replay only on the disposable devel copy."""
import base64
import csv
import io
import json
import os
from collections import Counter

from odoo.addons.import_partners.csv_source import FILES, load, select_rows

assert env.cr.dbname == 'devel_partner_import_test'  # noqa: F821
service = env['res.partner.csv.import.run']  # noqa: F821
per_file = int(os.environ.get('PARTNER_IMPORT_PER_FILE', '1000'))
assert per_file > 0, 'A finite positive per-file quota is required for this test'
directory = os.environ['PARTNER_CSV_DIR']
selected, source = select_rows(*load(directory), per_file_limit=per_file)
assert source['files'] == dict.fromkeys(FILES, per_file)
partners = env['res.partner'].with_context(active_test=False)  # noqa: F821
before = partners.search_count([])
kwargs = dict(expected_db=env.cr.dbname, batch_size=int(os.environ.get('PARTNER_IMPORT_BATCH', '100')),  # noqa: F821
              per_file_limit=per_file)
dry = service._run(directory, **kwargs)
assert partners.search_count([]) == before
applied = service._run(directory, dry_run=False, **kwargs)
after = partners.search_count([])
assert after - before == applied['counts'].get('created', 0)
assert applied['counts'] == dry['counts'], (dry['counts'], applied['counts'])
replay = service._run(directory, dry_run=False, **kwargs)
assert not replay['counts'].get('created'), replay
assert not replay['counts'].get('updated'), replay
assert partners.search_count([]) == after
for result in (dry, applied, replay):
    assert result['total'] == 3 * per_file
    assert all(sum(result['file_counts'][filename].values()) == per_file for filename in FILES)
reports = env['ir.attachment'].search([('res_model', '=', service._name), ('res_id', '=', applied['run_id'])])  # noqa: F821
excluded = set()
rejections = Counter()
for report in reports:
    for entry in csv.DictReader(io.StringIO(base64.b64decode(report.datas).decode('utf-8-sig')), delimiter=';'):
        if entry['status'] in ('rejected', 'supplier_protected'):
            excluded.add((entry['file'], int(entry['row'])))
        if entry['status'] == 'rejected':
            rejections[entry['reason']] += 1
defaults = service._lookups()
checked = Counter()
for row in selected:
    if (row['file'], row['row']) in excluded:
        continue
    partner = partners.with_company(env['res.company'].browse(row['company'])).search([  # noqa: F821
        ('company_id', '=', row['company']), ('codigo_bejerman', '=', row['key'])])
    assert len(partner) == 1, (row['file'], row['row'])
    assert partner.property_product_pricelist.id == defaults[row['company'], 'default_pricelist']
    assert partner.property_product_pricelist.company_id == partner.company_id
    assert partner.phone == (row['data']['Teléfono'] or False)
    assert partner.mobile_number == (row['data']['Numero de Celular'] or False)
    if row['parent_key']:
        assert partner.parent_id.codigo_bejerman == row['parent_key']
        assert partner.parent_id.company_id == partner.company_id
        assert partner.commercial_partner_id == partner.parent_id.commercial_partner_id
        assert partner.type == 'other'
    checked[row['company']] += 1
issues = dry.pop('issues')
dry['issue_counts'] = dict(Counter(r['reason'] for r in issues))
result = dict(source=source, sample_files=source['files'],
              dry=dry, apply=applied, replay=replay, checked_by_company=dict(checked),
              rejection_counts=dict(rejections),
              default_pricelist_ids={str(c): defaults[c, 'default_pricelist'] for c in (1, 8)},
              attachment_ids=reports.ids, partner_count_before=before, partner_count_after=after)
print('REAL_SAMPLE_RESULT=' + json.dumps(result, ensure_ascii=False))
