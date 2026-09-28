from odoo import fields, models


class LegalFolioRenumberWizard(models.TransientModel):
    _name = "ivess.legal.folio.renumber.wizard"
    _description = "Renumeración de Folio Legal"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    renumbered_count = fields.Integer(string="Asientos Renumerados", readonly=True)
    renumbered_move_ids = fields.Many2many(
        comodel_name="account.move",
        string="Asientos Renumerados",
        readonly=True,
    )

    def action_renumber(self):
        self.ensure_one()
        moves = self.env["account.move"]._ivess_renumber_legal_folio(self.company_id)
        self.renumbered_count = len(moves)
        self.renumbered_move_ids = [(6, 0, moves.ids)]
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
