from odoo import api, fields, models, tools

class IvessFiscalPositionReport(models.Model):
    _name = "ivess.fiscal.position.report"
    _description = "Vista SQL de posiciones fiscales expuesta al middleware Ivess"
    _auto = False

    name = fields.Char(translate=True, readonly=True)
    afip_code = fields.Integer(readonly=True)
    supplier_denomination = fields.Char(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    id,
                    name,
                    afip_code,
                    supplier_denomination
                FROM account_fiscal_position
            )
            """.format(table=self._table) 
        )

    @api.model
    def get_fiscal_positions(self):
        records = self.search([])
        return records.read(["name", "afip_code", "supplier_denomination"])
