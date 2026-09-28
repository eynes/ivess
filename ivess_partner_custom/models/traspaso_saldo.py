from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

CODIGO_DIARIO_TRASPASOS = "TRASP"


class IvessTraspasoSaldo(models.TransientModel):
    _name = "ivess.traspaso.saldo"
    _description = "Traspaso de saldo y baja de cuenta"

    origen_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cuenta que se da de baja",
        required=True,
        readonly=True,
    )
    destino_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cuenta destino",
        required=True,
        domain="[('id', '!=', origen_id)]",
    )
    observacion = fields.Text(
        string="Motivo",
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
    )
    saldo = fields.Monetary(
        string="Saldo a traspasar",
        compute="_compute_saldo",
        currency_field="currency_id",
    )
    deuda_en_madre = fields.Boolean(
        compute="_compute_deuda_en_madre",
    )
    hija_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Hijas activas",
        compute="_compute_hija_ids",
    )
    nueva_madre_id = fields.Many2one(
        comodel_name="res.partner",
        string="Nueva madre",
        domain="[('id', 'in', hija_ids)]",
    )

    @api.depends("origen_id")
    def _compute_hija_ids(self):
        for wizard in self:
            wizard.hija_ids = wizard.origen_id._hijas_activas() if wizard.origen_id else False

    @api.depends("origen_id")
    def _compute_deuda_en_madre(self):
        for wizard in self:
            origen = wizard.origen_id
            wizard.deuda_en_madre = bool(origen) and origen.commercial_partner_id != origen

    @api.depends("origen_id")
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = wizard.origen_id.company_id or self.env.company

    @api.depends("origen_id", "company_id")
    def _compute_saldo(self):
        for wizard in self:
            wizard.saldo = wizard._saldo_contable()

    def _saldo_contable(self):
        self.ensure_one()
        if not self.origen_id:
            return 0.0
        return self.origen_id._saldo_a_cobrar(self.company_id)

    def _diario_traspasos(self):
        journal = self.env["account.journal"].search(
            [
                ("code", "=", CODIGO_DIARIO_TRASPASOS),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not journal:
            # l10n_ar_eynes no deja postear en un diario sin período
            # (due_date): toma el mismo corte que los demás diarios de la
            # compañía, que el contador actualiza para todos juntos.
            cortes = (
                self.env["account.journal"]
                .search([("company_id", "=", self.company_id.id)])
                .mapped("due_date")
            )
            journal = self.env["account.journal"].sudo().create(
                {
                    "name": "Traspasos de Saldo",
                    "code": CODIGO_DIARIO_TRASPASOS,
                    "type": "general",
                    "company_id": self.company_id.id,
                    "due_date": max(filter(None, cortes), default=False),
                }
            )
        return journal

    def action_confirmar(self):
        self.ensure_one()
        origen, destino = self.origen_id, self.destino_id
        if destino.company_id and destino.company_id != self.company_id:
            raise UserError(
                _(
                    "No se puede traspasar el saldo a %(destino)s: es de %(cia_destino)s y la"
                    " cuenta que se da de baja es de %(cia_origen)s. Un asiento contable"
                    " pertenece a una sola compañía."
                )
                % {
                    "destino": destino.display_name,
                    "cia_destino": destino.company_id.name,
                    "cia_origen": self.company_id.name,
                }
            )
        if self.hija_ids and not self.nueva_madre_id:
            raise UserError(
                _("La cuenta tiene hijas activas: elegí cuál pasa a ser la nueva madre.")
            )
        saldo = self.saldo
        move = self.env["account.move"]
        if not self.currency_id.is_zero(saldo):
            move = self._crear_asiento(saldo)
        origen.write({"traspaso_destino_id": destino.id, "traspaso_move_id": move.id})
        monto = formatLang(self.env, saldo, currency_obj=self.currency_id)
        origen.message_post(
            body=_("Saldo de %(monto)s traspasado a %(destino)s%(asiento)s. Motivo: %(motivo)s")
            % {
                "monto": monto,
                "destino": destino.display_name,
                "asiento": (" (%s)" % move.name) if move else "",
                "motivo": self.observacion,
            }
        )
        destino.message_post(
            body=_("Recibió saldo de %(monto)s de %(origen)s%(asiento)s. Motivo: %(motivo)s")
            % {
                "monto": monto,
                "origen": origen.display_name,
                "asiento": (" (%s)" % move.name) if move else "",
                "motivo": self.observacion,
            }
        )
        if self.nueva_madre_id:
            origen._reasignar_hijas(self.nueva_madre_id)
        # Las facturas no se concilian (siguen impagas), pero su deuda ya está
        # en la cuenta destino: se archiva salteando solo ese control.
        origen.with_context(traspaso_saldo_hecho=True).write({"active": False})
        return {"type": "ir.actions.act_window_close"}

    def _crear_asiento(self, saldo):
        origen, destino = self.origen_id, self.destino_id
        cuenta_origen = origen.with_company(self.company_id).property_account_receivable_id
        cuenta_destino = destino.with_company(self.company_id).property_account_receivable_id
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self._diario_traspasos().id,
                "company_id": self.company_id.id,
                "date": fields.Date.context_today(self),
                "ref": _("Traspaso de saldo: %(origen)s → %(destino)s")
                % {"origen": origen.display_name, "destino": destino.display_name},
                "narration": self.observacion,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": destino.id,
                            "account_id": cuenta_destino.id,
                            "name": _("Saldo recibido de %s") % origen.display_name,
                            "debit": saldo if saldo > 0 else 0.0,
                            "credit": -saldo if saldo < 0 else 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": origen.id,
                            "account_id": cuenta_origen.id,
                            "name": _("Saldo traspasado a %s") % destino.display_name,
                            "debit": -saldo if saldo < 0 else 0.0,
                            "credit": saldo if saldo > 0 else 0.0,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move
