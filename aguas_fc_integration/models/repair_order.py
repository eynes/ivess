# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RepairOrder(models.Model):
    _inherit = "repair.order"

    embolsado_picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Traslado de embolsado",
        readonly=True,
        copy=False,
    )
    can_embolsado_a_expedicion = fields.Boolean(
        compute="_compute_can_embolsado_a_expedicion",
    )

    @api.depends("state", "repair_equipment_type", "is_outsourced")
    def _compute_can_embolsado_a_expedicion(self):
        for order in self:
            order.can_embolsado_a_expedicion = bool(
                order.id and not order._embolsado_bloqueo()
            )

    def _embolsado_bloqueo(self):
        """Motivo por el que la orden no puede pasar a expedición como embolsado,
        o False si puede."""
        self.ensure_one()
        if self.repair_equipment_type != "frio_calor":
            return _("Solo aplica a equipos de Frío/Calor.")
        if self.state in ("done", "cancel"):
            return _("La orden %s ya está finalizada o cancelada.", self.name)
        if self.is_outsourced:
            return _("La orden %s está tercerizada: primero debe recibirse del tercero.", self.name)
        batch = self._get_active_batch()
        if batch:
            return _(
                "La orden %(orden)s forma parte del lote '%(lote)s', que no está finalizado.",
                orden=self.name,
                lote=batch.name,
            )
        return False

    def _embolsado_sin_empezar(self):
        """Nadie empezó a trabajar la orden: confirmada, en prueba inicial, sin
        etapa iniciada, no tercerizada y fuera de un lote activo."""
        self.ensure_one()
        if self.state not in ("draft", "confirmed") or self.is_outsourced:
            return False
        if self.frio_calor_stage != "prueba_inicial":
            return False
        if any(
            not log.date_end and log.date_start for log in self.stage_log_ids
        ):
            return False
        return not self._get_active_batch()

    def action_embolsado_a_expedicion(self):
        for order in self:
            order._embolsado_a_expedicion()
        return True

    def _embolsado_a_expedicion(self, origin=None, motivo=None):
        """Cancela la orden y mueve el equipo, desde donde Odoo lo tiene, a la
        ubicación de expedición. Devuelve el traslado generado (vacío si el equipo
        ya estaba en expedición)."""
        self.ensure_one()
        motivo_bloqueo = self._embolsado_bloqueo()
        if motivo_bloqueo:
            raise UserError(motivo_bloqueo)

        intake = self.env["aguas.fc.intake"]
        company = self.company_id
        picking_type, expedicion = intake._embolsado_config(company)
        ubicaciones = intake._embolsado_ubicaciones(self.lot_id, company)
        if not ubicaciones:
            raise UserError(
                _(
                    "El equipo %s no tiene stock en Odoo, avisar a soporte.",
                    self.lot_id.name,
                )
            )

        now = fields.Datetime.now()
        open_log = self.stage_log_ids.filtered(lambda l: not l.date_end)[:1]
        if open_log and open_log.date_start:
            open_log.write({"date_end": now})

        self.action_repair_cancel()

        picking = self.env["stock.picking"]
        if not any(intake._embolsado_en_expedicion(l, expedicion) for l in ubicaciones):
            picking = intake._embolsado_crear_traslado(
                company, ubicaciones[0], self.lot_id, origin or self.name
            )
        self.embolsado_picking_id = picking

        user_id = self.env.context.get("_portal_user_id", self.env.user.id)
        usuario = self.env["res.users"].sudo().browse(user_id).name
        destino = (
            _("pasa a expedición en %s", picking.name)
            if picking
            else _("ya estaba en expedición, no se movió")
        )
        self.message_post(
            body=_(
                "Cancelada por %(usuario)s: %(motivo)s; %(destino)s.",
                usuario=usuario,
                motivo=motivo or _("el equipo volvió embolsado"),
                destino=destino,
            )
        )
        return picking
