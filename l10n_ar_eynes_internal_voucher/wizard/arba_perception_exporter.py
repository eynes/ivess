from odoo import _, models
from odoo.exceptions import ValidationError


class ArbaPerceptionExporterWizard(models.TransientModel):
    _inherit = 'arba.perception.exporter.wizard'

    def create_file(self):
        query = (
            'SELECT ptl.id '
            'FROM perception_tax_line ptl '
            'JOIN account_move ai ON ptl.invoice_id = ai.id '
            'JOIN account_tax at ON ptl.perception_id = at.id '
            'WHERE ptl.date BETWEEN %(date_from)s AND %(date_to)s '
            'AND ai.state IN %(state)s '
            'AND at.inform_arba = True '
            'AND at.retention_type IN %(type)s '
            'AND ai.company_id = %(company_id)s '
            'ORDER BY ptl.date '
        )
        cr = self.env.cr

        vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'state': ('posted', 'paid'),
            'type': ('gross_income',),
            'company_id': self.company_id.id,
        }

        cr.execute(query, vals)
        res = cr.fetchall()
        if not res:
            raise ValidationError(
                _(
                    'No perceptions found for export.\nHINT: Check if the '
                    'perceptions have the Inform ARBA field checked and/or if '
                    'the perceptions\'s type is \'gross income\''
                ),
            )

        perception_ids = [p[0] for p in res]

        # Excluir comprobantes internos (no se informan a ARBA)
        lines = self.env['perception.tax.line'].browse(perception_ids)
        lines = lines.filtered(
            lambda l: l.invoice_id.journal_id.fiscal_type != 'internal_voucher'
        )
        perception_ids = lines.ids
        if not perception_ids:
            raise ValidationError(
                _(
                    'No perceptions found for export.\nHINT: Check if the '
                    'perceptions have the Inform ARBA field checked and/or if '
                    'the perceptions\'s type is \'gross income\''
                ),
            )

        result = self._check_perception_tax_line_data(perception_ids)
        if isinstance(result, dict):
            raise ValidationError(result)

        self._generate_perception_file(perception_ids)
