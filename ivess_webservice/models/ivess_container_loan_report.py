from odoo import api, fields, models, tools


class IvessContainerLoanReport(models.Model):
    _name = "ivess.container.loan.report"
    _description = "Vista SQL de envases en comodato y prestados expuesta al middleware Ivess"
    _auto = False

    customer_code = fields.Char(readonly=True)
    default_code  = fields.Char(readonly=True)
    state_name    = fields.Char(readonly=True)
    return_date   = fields.Date(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    wc.id            AS id,
                    rp.customer_code AS customer_code,
                    pt.default_code  AS default_code,
                    wcs.name         AS state_name,
                    wc.return_date   AS return_date
                FROM water_container wc
                JOIN res_partner           rp  ON wc.partner_id = rp.id
                JOIN product_template      pt  ON wc.product_id = pt.id
                JOIN water_container_state wcs ON wc.state_id   = wcs.id
            )
            """.format(table=self._table)
        )

    @api.model
    def get_container_loans(self, customer_code=None):
        domain = [("customer_code", "=", customer_code)] if customer_code else []
        records = self.search(domain)
        return records.read(["default_code", "state_name", "return_date"])
