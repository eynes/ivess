from odoo import api, fields, models, tools

class IvessReplacementReasonReport(models.Model):
    _name = "ivess.replacement.reason.report"
    _description = "Vista SQL de motivos de recambio expuesta al middleware Ivess"
    _auto = False

    code = fields.Char(readonly=True)
    sequence = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    id,
                    code,
                    sequence
                FROM replacement_reason
            )
            """.format(table=self._table)
        )

    @api.model
    def get_replacement_reasons(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        records = self.search([])
        return records.read(["code", "sequence"])