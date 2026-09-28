from odoo import api, fields, models


class IvessBajaMadre(models.TransientModel):
    _name = "ivess.baja.madre"
    _description = "Baja de una cuenta madre con hijas activas"

    madre_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cuenta madre que se da de baja",
        required=True,
        readonly=True,
    )
    hija_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Hijas activas",
        compute="_compute_hija_ids",
    )
    nueva_madre_id = fields.Many2one(
        comodel_name="res.partner",
        string="Nueva madre",
        required=True,
        domain="[('id', 'in', hija_ids)]",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_saldo",
    )
    saldo = fields.Monetary(
        string="Saldo a cobrar de la madre",
        compute="_compute_saldo",
        currency_field="currency_id",
    )

    @api.depends("madre_id")
    def _compute_hija_ids(self):
        for wizard in self:
            wizard.hija_ids = wizard.madre_id._hijas_activas()

    @api.depends("madre_id")
    def _compute_saldo(self):
        for wizard in self:
            company = wizard.madre_id.company_id or self.env.company
            wizard.currency_id = company.currency_id
            wizard.saldo = wizard.madre_id._saldo_a_cobrar(company) if wizard.madre_id else 0.0

    def action_confirmar(self):
        self.ensure_one()
        self.madre_id._reasignar_hijas(self.nueva_madre_id)
        self.madre_id.action_archive()
        return {"type": "ir.actions.act_window_close"}
