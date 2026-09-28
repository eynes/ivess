from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class IvessVisitaFueraRuta(models.TransientModel):
    _name = "ivess.visita.fuera.ruta"
    _description = "Pedir visita fuera de ruta"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cliente",
        required=True,
        readonly=True,
    )
    fecha = fields.Date(
        string="Fecha",
        required=True,
        default=fields.Date.context_today,
    )
    reparto_id = fields.Many2one(
        comodel_name="delivery.route.number",
        string="Reparto",
        required=True,
        default=lambda self: self._default_reparto_id(),
    )
    route_id = fields.Many2one(
        comodel_name="delivery.route",
        string="Recorrido",
        compute="_compute_route_id",
    )
    franja_vencida = fields.Char(
        compute="_compute_franja_vencida",
    )

    @api.depends("fecha", "partner_id")
    def _compute_franja_vencida(self):
        ahora = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        hora_actual = ahora.hour + ahora.minute / 60.0
        for wizard in self:
            hasta = wizard.partner_id.visit_hour_to
            vencida = wizard.fecha == ahora.date() and hasta and hora_actual > hasta
            wizard.franja_vencida = (
                _("La franja horaria del cliente (hasta las %02d:%02d) ya pasó hoy.")
                % (int(hasta), round((hasta % 1) * 60))
                if vencida
                else False
            )

    def _default_reparto_id(self):
        partner = self.env["res.partner"].browse(self.env.context.get("default_partner_id"))
        repartos = partner.distributions_ids.distribution.delivery_number_id
        return repartos if len(repartos) == 1 else False

    @api.depends("fecha", "reparto_id")
    def _compute_route_id(self):
        for wizard in self:
            if not wizard.fecha or not wizard.reparto_id:
                wizard.route_id = False
                continue
            wizard.route_id = self.env["delivery.route"].search(
                [
                    ("delivery_date", "=", wizard.fecha),
                    ("delivery_number_id", "=", wizard.reparto_id.id),
                ],
                order="id",
                limit=1,
            )

    def action_confirmar(self):
        self.ensure_one()
        route = self.route_id
        if not route:
            raise UserError(
                _("No hay recorrido del reparto %(reparto)s para el %(fecha)s. Primero hay que generarlo.")
                % {"reparto": self.reparto_id.display_name, "fecha": format_date(self.env, self.fecha)}
            )
        if route.state == "closed":
            raise UserError(_("El recorrido %s ya está cerrado.") % route.display_name)
        if self.partner_id in route.delivery_route_line_ids.client_id:
            raise UserError(
                _("%(cliente)s ya está en el recorrido %(recorrido)s.")
                % {"cliente": self.partner_id.display_name, "recorrido": route.display_name}
            )
        self.env["delivery.route.line"].create(
            {
                "route_id": route.id,
                "client_id": self.partner_id.id,
                "origin": "fuera_de_ruta",
                "sequence": max(route.delivery_route_line_ids.mapped("sequence"), default=0) + 1,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Se agregó a %(cliente)s al recorrido %(recorrido)s.")
                % {"cliente": self.partner_id.display_name, "recorrido": route.display_name},
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
