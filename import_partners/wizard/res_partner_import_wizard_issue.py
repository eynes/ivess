from odoo import api, fields, models

# "Bloqueantes" son las que hacen que la fila NO se inserte en absoluto; el
# resto son advertencias sobre un campo puntual que queda en NULL pero el
# contacto se crea igual (ver res_partner_import_wizard._resolve_row).
BLOCKING_CATEGORIES = {"blank_name", "duplicate_bejerman", "already_imported"}

ISSUE_CATEGORIES = [
    ("blank_name", "Nombre vacío (fila excluida)"),
    ("duplicate_bejerman", "Código Bejerman repetido en el Excel (fila excluida)"),
    (
        "already_imported",
        "Ya existe en la base por código Bejerman o CUIT (fila excluida)",
    ),
    (
        "invalid_bejerman_format",
        "Código Bejerman con formato inválido (se guarda vacío)",
    ),
    ("unmatched_country", "País sin coincidencia (se guarda vacío)"),
    ("unmatched_state", "Provincia/Estado sin coincidencia (se guarda vacío)"),
    ("unmatched_doc_type", "Tipo de documento sin coincidencia (se guarda vacío)"),
    ("unmatched_afip_resp", "Posición fiscal sin coincidencia (se guarda vacío)"),
    ("unmatched_client_type", "Tipo de cliente sin coincidencia (se guarda vacío)"),
    (
        "invalid_vat_format",
        "CUIT/CUIL/DNI con dígito verificador inválido (se guarda vacío)",
    ),
]


class ResPartnerImportWizardIssue(models.TransientModel):
    _name = "res.partner.import.wizard.issue"
    _description = "Observación del análisis previo de importación de clientes"
    _order = "blocking desc, category, row_count desc"

    wizard_id = fields.Many2one(
        "res.partner.import.wizard", required=True, ondelete="cascade"
    )
    category = fields.Selection(ISSUE_CATEGORIES, required=True)
    blocking = fields.Boolean(compute="_compute_blocking", store=True)
    value = fields.Char(string="Valor en el Excel")
    row_count = fields.Integer(string="Filas afectadas")

    @api.depends("category")
    def _compute_blocking(self):
        for issue in self:
            issue.blocking = issue.category in BLOCKING_CATEGORIES
