"""Strict, deterministic CSV preflight; no Odoo dependency or database writes."""
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

VERSION = 17
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


def parse_exclude(value):
    """Parse 'file:row,file:row,...' into a set of (filename, row) pairs,
    e.g. from the PARTNER_IMPORT_EXCLUDE environment variable."""
    exclude = set()
    for token in filter(None, (value or '').split(',')):
        filename, _, row = token.strip().partition(':')
        exclude.add((filename, int(row)))
    return exclude


def load(directory, exclude=frozenset()):
    """exclude: a set of (filename, row) pairs to reject upfront, e.g. known
    source-data duplicates (same CUIT under two different customer codes)
    that an operator decided to skip rather than fix in the CSV itself."""
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
    # Candidate code for every row, mothers included, computed in its own
    # pass so a child (processed below regardless of file order) can always
    # compare against her already-resolved mother's candidate.
    for r in rows:
        code = r['data']['Código Bejerman']
        if code in ('', '0'):
            code = r['data']['Código de Cliente']
        r['_candidate'] = code
    for r in rows:
        data, filename = r['data'], r['file']
        candidates = r['parent_candidates']
        # A hija uses her own Bejerman (or Código de Cliente if blank/0),
        # like anyone else, unless it equals her mother's own resolved
        # code: that collision means the source only meant to identify the
        # mother, not give the hija a separate identity.
        if data['nrosub'] and len(candidates) == 1 and r['_candidate'] == candidates[0]['_candidate']:
            code = ''
        else:
            code = r['_candidate']
        error = ''
        if (filename, r['row']) in exclude:
            error = 'excluded_by_operator'
        elif not r['company'] or (filename == FILES[0] and r['company'] != 1) or (filename == FILES[1] and r['company'] != 8):
            error = 'invalid_company'
        elif not data['Código de Cliente'] or not data['Nombre'] or (not data['nrosub'] and not code):
            error = 'missing_identity_or_name'
        elif filename != FILES[2] and data['nrosub']:
            error = 'unexpected_parent'
        r['key'] = code
        r['error'] = error
    for r in rows:
        del r['_candidate']
    # A blank key (child sharing her mother's code) never collides: only
    # rows with an actual code participate in the duplicate-key check.
    counts = Counter((r['company'], r['key']) for r in rows if r['key'])
    for r in rows:
        if r['key'] and counts[r['company'], r['key']] > 1:
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
            # A mother excluded by an operator gets her own reason, distinct
            # from a genuinely missing one, so the cascade can be reported
            # separately (e.g. to notify the client which contacts were
            # skipped on purpose, as opposed to broken source data).
            if len(candidates) == 1 and candidates[0]['error'] == 'excluded_by_operator':
                r['error'] = r['error'] or 'mother_excluded_by_operator'
            elif len(candidates) != 1 or candidates[0]['error'] or candidates[0]['company'] != r['company']:
                r['error'] = r['error'] or 'missing_or_rejected_mother'
            else:
                r['parent_key'] = candidates[0]['key']
                r['parent_company'] = candidates[0]['company']
                r['parent_row'] = candidates[0]['row']
    # Mothers and standalone contacts precede all children, even across batches.
    rows.sort(key=lambda r: bool(r['data']['nrosub']))
    fingerprint = hashlib.sha256(json.dumps(
        [VERSION, hashes, sorted(exclude)], sort_keys=True).encode()).hexdigest()
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


def excluded_report(rows):
    """Rows an operator excluded directly, or that lost their mother to an
    exclusion (cascade): one line per row, ready to paste into a message to
    the client listing exactly which contacts were skipped and why."""
    reasons = {'excluded_by_operator': 'excluida a pedido del operador',
               'mother_excluded_by_operator': 'madre excluida a pedido del operador'}
    lines = []
    for r in sorted((r for r in rows if r['error'] in reasons), key=lambda r: (r['file'], r['row'])):
        lines.append('{file}:{row}\t{code}\t{name}\t{reason}'.format(
            file=r['file'], row=r['row'], code=r['data']['Código de Cliente'],
            name=r['data']['Nombre'], reason=reasons[r['error']]))
    return lines


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    parser.add_argument('--exclude', default='', help="'file:row,file:row,...'")
    args = parser.parse_args()
    rows, summary = load(args.directory, exclude=parse_exclude(args.exclude))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.exclude:
        report = excluded_report(rows)
        print(f'\n--- {len(report)} filas excluidas (directas + hijas en cascada) ---')
        print('archivo:línea\tcódigo\tnombre\tmotivo')
        print('\n'.join(report))
