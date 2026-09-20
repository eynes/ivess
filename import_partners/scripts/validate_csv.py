"""Read-only complete scalar/relation validation in an Odoo shell."""
import json
import os
from collections import Counter
from odoo.addons.import_partners.csv_source import load

rows, summary = load(os.environ['PARTNER_CSV_DIR'])
service = env['res.partner.csv.import.run']  # noqa: F821
lookups = service._lookups()
errors, warnings = Counter(), Counter()
for row in rows:
    if row['error']:
        errors[row['error']] += 1
        continue
    try:
        values, issues = service._values(row, lookups)
        warnings.update(issues)
    except ValueError as error:
        errors[str(error)] += 1
summary.update(validation_errors=dict(errors), warnings=dict(warnings),
               valid_scalar_and_relation_rows=len(rows) - sum(errors.values()))
print('CSV_VALIDATION_RESULT=' + json.dumps(summary, ensure_ascii=False))
env.cr.rollback()  # noqa: F821
