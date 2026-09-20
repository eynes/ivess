"""Execute with odoo shell, see docs/CSV_IMPORT.md. env comes from shell."""
import json
import os
from pathlib import Path

result = env['res.partner.csv.import.run']._run(  # noqa: F821
    os.environ['PARTNER_CSV_DIR'],
    expected_db=os.environ['PARTNER_IMPORT_DB'],
    dry_run=os.environ.get('PARTNER_IMPORT_APPLY') != 'yes',
    batch_size=int(os.environ.get('PARTNER_IMPORT_BATCH', '500')),
    limit=int(os.environ.get('PARTNER_IMPORT_LIMIT', '0')),
    per_file_limit=int(os.environ.get('PARTNER_IMPORT_PER_FILE', '1000')),
    run_id=int(os.environ['PARTNER_IMPORT_RUN']) if os.environ.get('PARTNER_IMPORT_RUN') else None,
)
output = json.dumps(result, ensure_ascii=False, indent=2)
if os.environ.get('PARTNER_IMPORT_RESULT'):
    Path(os.environ['PARTNER_IMPORT_RESULT']).write_text(output, encoding='utf-8')
print(output)
