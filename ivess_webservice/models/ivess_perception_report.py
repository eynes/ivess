from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools


class IvessPerceptionReport(models.Model):
    _name = "ivess.perception.report"
    _description = "Vista SQL de percepciones por cliente expuesta al middleware Ivess"
    _auto = False

    customer_code = fields.Char(readonly=True)
    perception_id = fields.Many2one("account.tax", readonly=True)
    tax_minimum = fields.Float(readonly=True)
    percent = fields.Float(readonly=True)
    period = fields.Date(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    rpp.id AS id,
                    rp.customer_code AS customer_code,
                    rpp.perception_id AS perception_id,
                    (
                        SELECT pta.tax_minimum
                        FROM perception_tax_application pta
                        WHERE pta.perception_tax_id = rpp.perception_id
                            AND pta.concept_id IS NULL
                            AND (
                                (rpp.activity_id IS NULL AND pta.activity_id IS NULL)
                                OR pta.activity_id = rpp.activity_id
                            )
                        LIMIT 1
                    ) AS tax_minimum,
                    rpp.percent AS percent,
                    rpp.period AS period
                FROM res_partner_perception rpp
                JOIN res_partner rp ON rpp.partner_id = rp.id
            )
            """.format(table=self._table)
        )

    @api.model
    def get_perceptions(self, customer_code, limit=None):
        today = fields.Date.today()
        lines = self.search([("customer_code", "=", customer_code)])

        result = []
        for perception in lines.mapped("perception_id"):
            perception_lines = lines.filtered(
                lambda l: l.perception_id == perception
            )
            match = perception_lines.filtered(
                lambda l: not l.period or (
                    l.period <= today
                    <= (l.period + relativedelta(months=1)) - relativedelta(days=1)
                )
            )
            if match:
                line = match[:1]
                result.append({
                    "perception_id": (perception.id, perception.display_name),
                    "tax_minimum": line.tax_minimum,
                    "percent": line.percent,
                })

        if limit:
            result = result[:limit]
        return result
