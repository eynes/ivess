from odoo import fields, models, tools, api

class IvessNoPurchaseReasonReport(models.Model):
    _name = "ivess.no.purchase.reason.report"
    _description = "Vista SQL de motivos de no compra expuesta al middleware Ivess"
    _auto = False

    reason = fields.Char(readonly=True)
    code = fields.Char(readonly=True)
    order = fields.Integer(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    id,
                    reason,
                    code,
                    "order"
                FROM no_purchase_reason
            )
            """.format(table=self._table)
        )

    @api.model
    def get_no_purchase_reasons(self, **kwargs):
        if kwargs:
            return {"error": "Este servicio no acepta parámetros. La request debe enviarse vacía."}
        records = self.search([])
        return records.read(["reason", "code", "order"])