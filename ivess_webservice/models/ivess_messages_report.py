from odoo import api, fields, models, tools

class IvessMessagesReport(models.Model):
    _name = "ivess.messages.report"
    _description = "Vista SQL de mensajes expuesta al middleware Ivess"
    _auto = False

    street = fields.Char(readonly=True)
    visit_hour_from = fields.Float(readonly=True)
    visit_hour_to = fields.Float(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ivess_messages_report AS (
                SELECT
                id,
                street,
                visit_hour_from,
                visit_hour_to
                FROM res_partner
            )
        """)