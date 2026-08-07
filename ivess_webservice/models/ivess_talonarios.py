from odoo import api, fields, models, tools

class IvessTalonariosReport(models.Model):
    _name = "ivess.talonarios.report"
    _description = "Vista SQL de talonarios expuesta al middleware Ivess"
    _auto = False

    number = fields.Integer(readonly=True)
    
    #Campos Many2one
    remittance_sequence_id = fields.Many2one("ir.sequence", readonly=True)
    collection_journal_id = fields.Many2one("account.journal", readonly=True)
    repair_order_sequence_id = fields.Many2one("ir.sequence", readonly=True)

    #Campos related
    rem_next_number = fields.Integer(
        related="remittance_sequence_id.number_next_actual",
        readonly=True
        )
    rec_next_number = fields.Integer(
        related="collection_journal_id.sequence_number_next",
        readonly=True
        )
    or_next_number = fields.Integer(
        related="repair_order_sequence_id.number_next_actual",
        readonly=True
        )
    rem_prefix = fields.Char(
        related="remittance_sequence_id.prefix",
        readonly=True
        )
    rec_prefix = fields.Char(
        related="collection_journal_id.code",
        readonly=True
        )
    or_prefix = fields.Char(
        related="repair_order_sequence_id.prefix",
        readonly=True
        )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT 
                drn.id AS id,
                drn.number AS number,
                drn.remittance_sequence_id AS remittance_sequence_id,
                drn.collection_journal_id AS collection_journal_id,
                drn.repair_order_sequence_id AS repair_order_sequence_id          
                FROM delivery_route_number drn
                )
                """.format(table=self._table)
        )

    @api.model
    def get_talonarios(self, **kwargs):
        allowed_params = {"distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: distribution."
                        % ", ".join(sorted(unknown_params))
            }
        distribution = kwargs.get("distribution")
        if not distribution:
            return {
                "error": "Se requiere el parámetro distribution."
            }
        if not type(distribution) is int:
            return {
                "error": "El parámetro 'distribution' debe ser un entero. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        delivery = self.env['delivery.route.number'].search([('number', '=', distribution)], limit=1)
        if not delivery:
            return {"error": "No existe un reparto con el número '%s'." % distribution}

        record = self.browse(delivery.id)

        #chequeo de talonarios asociados (ver si estan configurados en el reparto)
        has_remittance_sequence = bool(record.remittance_sequence_id)
        has_collection_journal = bool(record.collection_journal_id)
        has_repair_order_sequence = bool(record.repair_order_sequence_id)

        return {
            "distribution": distribution,
            "rem_next_number": record.rem_next_number if has_remittance_sequence else None,
            "rem_prefix": record.rem_prefix if has_remittance_sequence else None,
            "rec_next_number": record.rec_next_number if has_collection_journal else None,
            "rec_prefix": record.rec_prefix if has_collection_journal else None,
            "or_next_number": record.or_next_number if has_repair_order_sequence else None,
            "or_prefix": record.or_prefix if has_repair_order_sequence else None
        }