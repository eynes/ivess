from odoo import api, fields, models, tools

class IvessLimitFreeOfChargeReport(models.Model):
    _name = "ivess.limit.free.of.charge.report"
    _description = "Vista SQL de límites de sin cargo expuesta al middleware Ivess"
    _auto = False

    default_code = fields.Char(readonly=True)

    def init(self):
          tools.drop_view_if_exists(self.env.cr, self._table)
          self.env.cr.execute("""
              CREATE OR REPLACE VIEW ivess_limit_free_of_charge_report AS (
                  SELECT
                      id,
                      default_code
                  FROM product_template
              )
          """)
