from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.addons.logistic_custom_ivess.models.visit_schedule_mixin import WEEKDAY_MAPPING
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date

# Odoo.sh corre en UTC y los usuarios pueden no tener zona horaria: la fecha y la
# hora de los pedidos son siempre las de Argentina.
AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


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
        default=lambda self: self._ahora_ar().date(),
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
    fuera_de_hora = fields.Char(
        compute="_compute_fuera_de_hora",
    )
    reparto_distinto = fields.Char(
        compute="_compute_reparto_distinto",
    )

    @api.model
    def _ahora_ar(self):
        return datetime.now(AR_TZ)

    @api.constrains("fecha")
    def _check_fecha_no_pasada(self):
        hoy = self._ahora_ar().date()
        for wizard in self:
            if wizard.fecha and wizard.fecha < hoy:
                raise ValidationError(
                    _("No se puede pedir una visita para una fecha pasada (%(fecha)s). Elegí hoy o una fecha posterior.")
                    % {"fecha": format_date(self.env, wizard.fecha)}
                )

    @api.depends("fecha")
    def _compute_fuera_de_hora(self):
        # Minuta del 24/09/2026: los pedidos cargados después de la hora límite
        # (15 hs por defecto, Ajustes > Ventas) se avisan, no se bloquean.
        limite = float(
            self.env["ir.config_parameter"].sudo().get_param("logistic_custom_ivess.hora_limite_pedidos")
            or 15.0
        )
        ahora = self._ahora_ar()
        pasada = ahora.hour + ahora.minute / 60.0 > limite
        for wizard in self:
            wizard.fuera_de_hora = (
                _("Ya pasó la hora límite de pedidos (%02d:%02d): normalmente se agenda para el día siguiente.")
                % (int(limite), round((limite % 1) * 60))
                if pasada and wizard.fecha == ahora.date()
                else False
            )

    @api.depends("fecha", "partner_id")
    def _compute_franja_vencida(self):
        ahora = self._ahora_ar()
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
        return self._proponer_reparto(partner, self._ahora_ar().date())

    def _proponer_reparto(self, partner, fecha):
        """Reparto habitual del cliente. Si tiene más de uno, el que le toca el
        día de la semana de la fecha o, si ese día no le toca ninguno, el de
        su día de visita siguiente. Los repartos técnicos (frío/calor,
        instalaciones, retiros) nunca se proponen para un pedido."""
        plantillas = partner.distributions_ids.distribution.filtered(
            lambda plantilla: plantilla.delivery_number_id
            and not plantilla.delivery_number_id.is_technical_delivery
        )
        repartos = plantillas.delivery_number_id
        if len(repartos) <= 1 or not fecha:
            return repartos[:1]
        # No hay empates: un cliente no puede tener dos plantillas el mismo día.
        return min(
            plantillas,
            key=lambda plantilla: (WEEKDAY_MAPPING[plantilla.day] - fecha.weekday()) % 7,
        ).delivery_number_id

    @api.onchange("fecha")
    def _onchange_fecha_proponer_reparto(self):
        # Un reparto ajeno al cliente se eligió a propósito: no se pisa.
        if not self.reparto_id or self.reparto_id in self._repartos_habituales():
            self.reparto_id = self._proponer_reparto(self.partner_id, self.fecha)

    def _repartos_habituales(self):
        self.ensure_one()
        return self.partner_id.distributions_ids.distribution.delivery_number_id

    @api.depends("partner_id", "reparto_id")
    def _compute_reparto_distinto(self):
        # Minuta del 01/10/2026: mandar la visita por un reparto que no es el
        # del cliente pide una aceptación aparte y queda en su historial.
        for wizard in self:
            habituales = wizard._repartos_habituales()
            if not wizard.reparto_id or not habituales or wizard.reparto_id in habituales:
                wizard.reparto_distinto = False
                continue
            nombres = ", ".join(habituales.sorted("number").mapped("display_name"))
            wizard.reparto_distinto = (
                _("El reparto habitual del cliente es el %(habituales)s y elegiste el %(elegido)s.")
                if len(habituales) == 1
                else _("Los repartos habituales del cliente son %(habituales)s y elegiste el %(elegido)s.")
            ) % {"habituales": nombres, "elegido": wizard.reparto_id.display_name}

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
        if self.reparto_distinto and not self.env.context.get("reparto_distinto_aceptado"):
            raise UserError(
                _("%s Hay que aceptar el cambio de reparto para agregar la visita.") % self.reparto_distinto
            )
        self.env["delivery.route.line"].create(
            {
                "route_id": route.id,
                "client_id": self.partner_id.id,
                "origin": "fuera_de_ruta",
                "sequence": max(route.delivery_route_line_ids.mapped("sequence"), default=0) + 1,
            }
        )
        if self.reparto_distinto:
            self.partner_id.message_post(
                body=_(
                    "Visita fuera de ruta del %(fecha)s asignada al reparto %(elegido)s,"
                    " que no es su reparto habitual (%(habituales)s). Recorrido: %(recorrido)s."
                )
                % {
                    "fecha": format_date(self.env, self.fecha),
                    "elegido": self.reparto_id.display_name,
                    "habituales": ", ".join(
                        self._repartos_habituales().sorted("number").mapped("display_name")
                    ),
                    "recorrido": route.display_name,
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
