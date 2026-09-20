"""Real commits/rollback integration test. ONLY on the named disposable copy."""
import csv
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from odoo.addons.import_partners.csv_source import FILES, HEADERS

assert env.cr.dbname == 'devel_partner_import_test'  # noqa: F821
service = env['res.partner.csv.import.run']  # noqa: F821
partners = env['res.partner'].with_context(active_test=False)  # noqa: F821
prefix = 'CSV-TXN-' + uuid.uuid4().hex[:8] + '-'
assert not partners.search_count([('codigo_bejerman', 'like', prefix + '%')]), 'Use a fresh copy for this test'
with tempfile.TemporaryDirectory() as directory:
    for filename in FILES:
        with (Path(directory) / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
            writer.writeheader()
            if filename == FILES[0]:
                for n in range(4):
                    row = dict.fromkeys(HEADERS, '')
                    row.update({'Nombre': f'Transaction test {n}', 'Código de Cliente': prefix + str(n),
                                'Código Bejerman': prefix + str(n), 'Empresa': 'El Jumillano S.A.',
                                'Tipo de empresa': 'PERSONA', 'País': 'ARGENTINA'})
                    if n == 1:
                        row['Geo latitud'] = 'bad-number'
                    writer.writerow(row)
    kwargs = dict(expected_db=env.cr.dbname, batch_size=2)  # noqa: F821
    before = partners.search_count([])
    attachment_before = env['ir.attachment'].search_count([])  # noqa: F821
    dry = service._run(directory, **kwargs)
    assert dry['counts'] == {'created': 3, 'rejected': 1}, dry
    assert partners.search_count([]) == before
    assert env['ir.attachment'].search_count([]) == attachment_before  # noqa: F821
    first = service._run(directory, dry_run=False, limit=2, **kwargs)
    assert first['checkpoint'] == 2
    assert first['file_counts'][FILES[0]] == {'created': 1, 'rejected': 1}
    assert partners.search_count([]) == before + 1
    run = service.browse(first['run_id'])
    assert run.checkpoint == 2
    # Fatal failure rolls back only the current batch; checkpoint stays at 2.
    original = type(service)._apply_row
    def interrupt(self, row, lookups):
        if row['key'].endswith('3'):
            raise RuntimeError('simulated interruption')
        return original(self, row, lookups)
    with patch.object(type(service), '_apply_row', interrupt):
        try:
            service._run(directory, dry_run=False, run_id=run.id, **kwargs)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Expected interruption')
    assert run.checkpoint == 2
    assert partners.search_count([]) == before + 1
    resumed = service._run(directory, dry_run=False, run_id=run.id, **kwargs)
    assert resumed['counts'] == {'created': 3, 'rejected': 1}, resumed
    assert run.state == 'done'
    assert resumed['file_counts'][FILES[0]] == resumed['counts']
    assert run.file_counts == resumed['file_counts']
    replay = service._run(directory, dry_run=False, **kwargs)
    assert replay['counts'] == {'unchanged': 3, 'rejected': 1}, replay
    assert partners.search_count([]) == before + 3
    assert env['ir.attachment'].search_count([('res_model', '=', service._name), ('res_id', '=', run.id)]) == 2  # noqa: F821
    with (Path(directory) / FILES[0]).open('a') as stream:
        stream.write('\n')
    try:
        service._run(directory, dry_run=False, run_id=run.id, **kwargs)
    except Exception as error:
        assert 'changed input' in str(error), error
    else:
        raise AssertionError('Changed files must block resume')
# Exercise the per-file quota through real checkpoint commits, including resume.
with tempfile.TemporaryDirectory() as directory:
    for file_index, filename in enumerate(FILES):
        with (Path(directory) / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=';')
            writer.writeheader()
            for number in range(4):
                code = f'{prefix}QUOTA-{file_index}-{number}'
                row = dict.fromkeys(HEADERS, '')
                row.update({'Nombre': code, 'Código de Cliente': code, 'Código Bejerman': code,
                            'Empresa': 'Lufrán S.A.' if file_index == 1 else 'El Jumillano S.A.',
                            'Tipo de empresa': 'PERSONA', 'País': 'ARGENTINA'})
                writer.writerow(row)
    quota_kwargs = dict(expected_db=env.cr.dbname, batch_size=2, dry_run=False)  # noqa: F821
    partial = service._run(directory, per_file_limit=2, limit=3, **quota_kwargs)
    assert partial['checkpoint'] == 3 and partial['total'] == 6
    try:
        service._run(directory, per_file_limit=3, run_id=partial['run_id'], **quota_kwargs)
    except Exception as error:
        assert 'changed input/version' in str(error), error
    else:
        raise AssertionError('Changing the sample quota must block resume')
    quota_resume = service._run(directory, per_file_limit=2, run_id=partial['run_id'], **quota_kwargs)
    assert quota_resume['counts'] == {'created': 6}, quota_resume
    assert quota_resume['file_counts'] == {filename: {'created': 2} for filename in FILES}
    assert quota_resume['checkpoint'] == 6
print(json.dumps({'transaction_tests': 'PASS', 'dry_run': dry['counts'], 'resumed': resumed['counts'], 'replay': replay['counts'], 'per_file_resume': quota_resume['file_counts']}))
