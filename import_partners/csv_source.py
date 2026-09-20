"""Strict, deterministic CSV preflight; no Odoo dependency or database writes."""
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

VERSION = 10
COMPANIES = {'El Jumillano S.A.': 1, 'Lufrán S.A.': 8}
FILES = ('page_clientes_jumillano.csv', 'page_clientes_lufran.csv',
         'page_ctas_madres_hijas_all.csv')
HEADERS = ('Nombre', 'Código de Cliente', 'Código Bejerman', 'Es Cliente',
           'Es Proveedor', 'nrosub', 'Tipo de empresa', 'Correo electronico',
           'Teléfono', 'Numero de Celular', 'Observaciones de Direccion',
           'Calle', 'País', 'Ciudad', 'Estado', 'Tipo de Documento', 'NrCUIT',
           'Cliente Importante', 'Fecha de Alta', 'Precios Especiales',
           'Posición fiscal', 'Tipo de cliente', 'Cuenta por Cobrar',
           'Requiere Comprobante', 'Geo latitud', 'Geo longitud', 'Etiqueta',
           'Distribuciones', 'Días', 'Horario promedio', 'Empresa',
           'Términos de pago del cliente', 'ListaPrecio', 'Zona venta')


def clean(value):
    value = value.strip()
    return '' if value.upper() == 'NULL' else value


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.strip().casefold())
                   if not unicodedata.combining(c))


def load(directory):
    rows, hashes = [], {}
    for filename in FILES:
        path = Path(directory) / filename
        hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream, delimiter=';', strict=True)
            if tuple(reader.fieldnames or ()) != HEADERS:
                raise ValueError(f'{filename}: unexpected headers')
            for number, raw in enumerate(reader, 2):
                if None in raw or None in raw.values():
                    raise ValueError(f'{filename}:{number}: malformed row')
                data = {k: clean(v) for k, v in raw.items()}
                company = next((cid for name, cid in COMPANIES.items()
                                if normalize(name) == normalize(data['Empresa'])), None)
                rows.append(dict(file=filename, row=number, data=data, raw=raw, company=company))
    # nrosub links to the mother's Código de Cliente alone: some mothers and
    # children are tagged with a different Empresa in the source data, and
    # each keeps its own company on import rather than being forced to match.
    customers = defaultdict(list)
    for r in rows:
        if r['file'] == FILES[2] and not r['data']['nrosub']:
            customers[r['data']['Código de Cliente']].append(r)
    for r in rows:
        r['parent_candidates'] = customers[r['data']['nrosub']] if r['data']['nrosub'] else []
    for r in rows:
        data, filename = r['data'], r['file']
        # Código Bejerman only identifies the mother. Every child is left
        # with no code at all: she is identified by Código de Cliente
        # instead (see csv_import_run._apply_row), never by Bejerman.
        if data['nrosub']:
            code = ''
        else:
            code = data['Código Bejerman']
            if code in ('', '0'):
                code = 'SC-' + data['Código de Cliente'] if data['Código de Cliente'] else ''
        error = ''
        if not r['company'] or (filename == FILES[0] and r['company'] != 1) or (filename == FILES[1] and r['company'] != 8):
            error = 'invalid_company'
        elif not data['Código de Cliente'] or not data['Nombre'] or (not data['nrosub'] and not code):
            error = 'missing_identity_or_name'
        elif filename != FILES[2] and data['nrosub']:
            error = 'unexpected_parent'
        r['key'] = code
        r['error'] = error
    # Children have no Bejerman-based identity, so they never participate in
    # the duplicate-key check: only mothers and standalone contacts do.
    counts = Counter((r['company'], r['key']) for r in rows if not r['data']['nrosub'])
    for r in rows:
        if not r['data']['nrosub'] and counts[r['company'], r['key']] > 1:
            r['error'] = r['error'] or 'duplicate_key'
    for r in rows:
        r['parent_key'] = ''
        r['parent_company'] = None
        r['parent_row'] = None
        candidates = r.pop('parent_candidates')
        if r['data']['nrosub']:
            # A mother tagged with a different Empresa than her child is not
            # a valid link: verify the company explicitly and reject it as a
            # missing mother rather than silently accepting the mismatch.
            if len(candidates) != 1 or candidates[0]['error'] or candidates[0]['company'] != r['company']:
                r['error'] = r['error'] or 'missing_or_rejected_mother'
            else:
                r['parent_key'] = candidates[0]['key']
                r['parent_company'] = candidates[0]['company']
                r['parent_row'] = candidates[0]['row']
    # Mothers and standalone contacts precede all children, even across batches.
    rows.sort(key=lambda r: bool(r['data']['nrosub']))
    fingerprint = hashlib.sha256(json.dumps([VERSION, hashes], sort_keys=True).encode()).hexdigest()
    summary = dict(total=len(rows), files=dict(Counter(r['file'] for r in rows)),
                   rejected=dict(Counter(r['error'] for r in rows if r['error'])),
                   fingerprint=fingerprint, hashes=hashes)
    return rows, summary


def select_rows(rows, summary, per_file_limit=0):
    """Select an exact quota per source, keeping global errors and source row IDs.

    Children reserve a slot for their valid mother. Both count toward the quota.
    No rows are reparsed, so a duplicate outside the sample cannot become valid.
    """
    if per_file_limit < 0:
        raise ValueError('per_file_limit must be nonnegative')
    if not per_file_limit:
        return rows, summary
    selected_ids = set()
    for filename in FILES:
        candidates = sorted((r for r in rows if r['file'] == filename), key=lambda r: r['row'])
        if len(candidates) < per_file_limit:
            raise ValueError(f'{filename}: fewer than {per_file_limit} source rows')
        chosen = set()
        for row in candidates:
            required = {row['row']}
            if row['parent_row'] is not None and not row['error']:
                required.add(row['parent_row'])
            if len(chosen | required) <= per_file_limit:
                chosen.update(required)
            if len(chosen) == per_file_limit:
                break
        if len(chosen) != per_file_limit:
            raise ValueError(f'{filename}: cannot satisfy quota with mothers included')
        selected_ids.update((filename, number) for number in chosen)
    selected = [row for row in rows if (row['file'], row['row']) in selected_ids]
    result = dict(summary)
    result.update(source_total=summary['total'], source_files=summary['files'],
                  source_rejected=summary['rejected'], source_fingerprint=summary['fingerprint'],
                  per_file_limit=per_file_limit, total=len(selected),
                  files=dict(Counter(r['file'] for r in selected)),
                  rejected=dict(Counter(r['error'] for r in selected if r['error'])))
    result['fingerprint'] = hashlib.sha256(json.dumps([
        summary['fingerprint'], per_file_limit, sorted(selected_ids)
    ], sort_keys=True).encode()).hexdigest()
    return selected, result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    args = parser.parse_args()
    print(json.dumps(load(args.directory)[1], ensure_ascii=False, indent=2))
