from odoo.addons.ivess_accounting_summary.translation_repair import (
    repair_es_ar_translations,
)


def migrate(cr, version):
    repair_es_ar_translations(cr)
