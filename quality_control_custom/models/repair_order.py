# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


FRIO_CALOR_STAGES = [
    ('repair', 'Reparación'),
    ('prueba_inicial', 'Prueba inicial'),
    ('hidrolavadora', 'Limpieza con hidrolavadora'),
    ('pileta', 'Lavado en pileta'),
    ('prueba', 'Prueba y sanitización'),
    ('secado', 'Secado'),
    ('pintura', 'Pintura'),
    ('armado', 'Embolsado'),
    ('finalizado', 'Finalizado'),
    ('descarte', 'Descarte'),
]

# Etapas excluidas del orden de navegación secuencial: tienen botones dedicados.
_STAGES_OUT_OF_ORDER = frozenset({'finalizado', 'pintura', 'descarte'})
FRIO_CALOR_STAGE_ORDER = [s[0] for s in FRIO_CALOR_STAGES if s[0] not in _STAGES_OUT_OF_ORDER]
# Orden sin pintura
FRIO_CALOR_STAGE_ORDER_NO_PAINT = [s for s in FRIO_CALOR_STAGE_ORDER if s != 'pintura']


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    repair_equipment_type = fields.Selection(
        related='product_id.product_tmpl_id.repair_equipment_type',
        string="Tipo de equipo para reparación",
        readonly=True,
        store=True,
    )

    frio_calor_stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string="Etapa Frío/Calor",
        default='prueba_inicial',
        tracking=True,
    )

    prueba_inicial_resultado = fields.Selection(
        selection=[
            ('no_definido', 'No definido'),
            ('aprobado', 'Aprobado'),
            ('desaprobado', 'Desaprobado'),
        ],
        string="Resultado prueba inicial",
        default='no_definido',
    )

    prev_frio_calor_stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string="Etapa Frío/Calor Anterior",
        readonly=True,
        copy=False
    )

    requires_painting = fields.Boolean(
        string="Requiere pintura",
        default=False,
    )

    is_outsourced = fields.Boolean(
        string="Tercerizado",
        default=False,
    )

    quality_check_id = fields.Many2one(
        comodel_name='quality.check',
        string="Control de Calidad Origen",
        readonly=True,
        copy=False,
    )

    outsource_transfer_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Traslado de Tercerización",
        readonly=True,
        copy=False,
    )
    outsource_reason_id = fields.Many2one(
        comodel_name='repair.outsource.reason',
        string="Razón de tercerización",
        readonly=True,
        copy=False,
    )

    stage_log_ids = fields.One2many(
        'repair.order.stage.log',
        'repair_id',
        string='Historial de Etapas',
    )

    stage_started = fields.Boolean(
        compute='_compute_stage_started',
        string="Etapa iniciada",
    )

    @api.depends('stage_log_ids.date_start', 'stage_log_ids.date_end', 'repair_equipment_type', 'frio_calor_stage')
    def _compute_stage_started(self):
        for order in self:
            if order.repair_equipment_type != 'frio_calor':
                order.stage_started = True
                continue
            open_log = order.stage_log_ids.filtered(lambda l: not l.date_end)
            order.stage_started = bool(open_log and open_log[0].date_start)

    def action_start_current_stage(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_("Confirme la orden de reparación antes de comenzar la etapa."))
        open_log = self.stage_log_ids.filtered(lambda l: not l.date_end and not l.date_start)
        if not open_log:
            return
        open_log[0].date_start = fields.Datetime.now()
        stage_name = dict(FRIO_CALOR_STAGES).get(self.frio_calor_stage, self.frio_calor_stage)
        self.message_post(body=_("Etapa '%s' iniciada.", stage_name))

    def _get_stage_sequence(self):
        """Retorna la secuencia de etapas según requires_painting."""
        self.ensure_one()
        if self.requires_painting:
            return FRIO_CALOR_STAGE_ORDER
        return FRIO_CALOR_STAGE_ORDER_NO_PAINT

    def action_next_frio_calor_stage(self):
        for order in self:
            if order.repair_equipment_type != 'frio_calor':
                raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
            if order.is_outsourced:
                raise UserError(_("No se puede avanzar la etapa de una orden tercerizada."))
            stages = order._get_stage_sequence()
            current = order.frio_calor_stage
            if current not in stages:
                raise UserError(_("Etapa actual '%s' no es válida en la secuencia.", current))
            current_idx = stages.index(current)
            if current_idx >= len(stages) - 1:
                raise UserError(_("La orden ya se encuentra en la última etapa."))
            next_stage = stages[current_idx + 1]
            order.with_context(_frio_calor_stage_advance=True).frio_calor_stage = next_stage
            order.message_post(
                body=_("Etapa avanzada de '%s' a '%s'.",
                       dict(FRIO_CALOR_STAGES).get(current, current),
                       dict(FRIO_CALOR_STAGES).get(next_stage, next_stage)),
            )

    def action_prev_frio_calor_stage(self):
        for order in self:
            if order.repair_equipment_type != 'frio_calor':
                raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
            if order.is_outsourced:
                raise UserError(_("No se puede revertir la etapa de una orden tercerizada."))
            stages = order._get_stage_sequence()
            current = order.frio_calor_stage
            if current not in stages:
                raise UserError(_("Etapa actual '%s' no es válida en la secuencia.", current))
            current_idx = stages.index(current)
            if current_idx == 0:
                raise UserError(_("La orden ya se encuentra en la primera etapa."))
            prev_stage = stages[current_idx - 1]
            order.with_context(_revert_stage=True).frio_calor_stage = prev_stage
            order.message_post(
                body=_("Etapa revertida de '%s' a '%s'.",
                       dict(FRIO_CALOR_STAGES).get(current, current),
                       dict(FRIO_CALOR_STAGES).get(prev_stage, prev_stage)),
            )

    def action_open_advance_next_stage(self):
        self.ensure_one()
        if self.repair_equipment_type != 'frio_calor':
            raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
        if self.is_outsourced:
            raise UserError(_("No se puede avanzar la etapa de una orden tercerizada."))
        if not self.stage_started:
            raise UserError(_("Debe iniciar la etapa actual presionando 'Comenzar' antes de avanzar."))
        if self.frio_calor_stage == 'prueba_inicial':
            self.message_post(
                body=_("El resultado de la prueba inicial de la orden fue '%s'.", self.prueba_inicial_resultado),
            )
        stages = self._get_stage_sequence()
        current_idx = stages.index(self.frio_calor_stage) if self.frio_calor_stage in stages else -1
        self.with_context(_frio_calor_stage_advance=True).write({'frio_calor_stage': stages[current_idx + 1]})

    def action_open_advance_stage_wizard(self):
        self.ensure_one()
        if self.repair_equipment_type != 'frio_calor':
            raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
        if self.is_outsourced:
            raise UserError(_("No se puede avanzar la etapa de una orden tercerizada."))
        stages = self._get_stage_sequence()
        current_idx = stages.index(self.frio_calor_stage) if self.frio_calor_stage in stages else -1
        stage_dict = dict(FRIO_CALOR_STAGES)
        wizard = self.env['repair.order.advance.stage.wizard'].create({
            'repair_id': self.id,
            'current_stage': self.frio_calor_stage,
            'valid_stage_ids': [
                (0, 0, {'key': k, 'name': stage_dict[k], 'sequence': i})
                for i, k in enumerate(stages[current_idx + 1:])
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Avanzar Etapa'),
            'res_model': 'repair.order.advance.stage.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_open_revert_stage_wizard(self):
        self.ensure_one()
        if self.repair_equipment_type != 'frio_calor':
            raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
        if self.is_outsourced:
            raise UserError(_("No se puede revertir la etapa de una orden tercerizada."))
        stages = self._get_stage_sequence()
        current_idx = stages.index(self.frio_calor_stage) if self.frio_calor_stage in stages else 0
        stage_dict = dict(FRIO_CALOR_STAGES)
        wizard = self.env['repair.order.revert.stage.wizard'].create({
            'repair_id': self.id,
            'current_stage': self.frio_calor_stage,
            'valid_stage_ids': [
                (0, 0, {'key': k, 'name': stage_dict[k], 'sequence': i})
                for i, k in enumerate(stages[:current_idx])
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revertir Etapa'),
            'res_model': 'repair.order.revert.stage.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_outsource(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tercerizar'),
            'res_model': 'repair.outsource.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_repair_id': self.id},
        }

    def _do_outsource(self, reason=None):
        self.ensure_one()
        order = self
        stage_label = dict(FRIO_CALOR_STAGES).get(order.frio_calor_stage, order.frio_calor_stage)

        internal_picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', 'in', [order.company_id.id, False]),
        ], limit=1)
        if not internal_picking_type:
            raise UserError(_("No se encontró un tipo de operación de traslado interno."))

        dest_location = order.company_id.tercerizacion_location_id
        if not dest_location:
            raise UserError(_(
                "No se configuró la ubicación de tercerización para la empresa '%s'. "
                "Configúrela en la ficha de la empresa."
            ) % order.company_id.name)

        source_location = order.location_id or internal_picking_type.default_location_src_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': internal_picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'origin': _("Tercerización etapa: %s - %s - %s") % (stage_label, order.name, dest_location.display_name),
            'outsource_reason_id': reason.id if reason else False,
            'move_ids': [(0, 0, {
                'product_id': order.product_id.id,
                'product_uom_qty': order.product_qty,
                'product_uom': order.product_uom.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            })],
        })
        picking.action_confirm()

        order.with_context(_outsource_action=True).write({
            'is_outsourced': True,
            'outsource_transfer_id': picking.id,
            'outsource_reason_id': reason.id if reason else False,
        })
        order.message_post(
            body=_("La orden fue tercerizada desde la etapa '%s'. Se generó el traslado %s hacia %s.", stage_label, picking.name, dest_location.display_name),
        )

    def action_receive_from_third_party(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recibir de tercero'),
            'res_model': 'repair.receive.third.party.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_repair_id': self.id},
        }

    def _do_receive_from_third_party(self, target_stage):
        self.ensure_one()
        self.with_context(
            _outsource_action=True,
            _frio_calor_stage_advance=True,
        ).write({
            'is_outsourced': False,
            'frio_calor_stage': target_stage,
        })
        stage_name = dict(FRIO_CALOR_STAGES).get(target_stage, target_stage)
        self.message_post(body=_(
            "La orden fue recibida del tercero. Etapa reiniciada a '%s'.", stage_name
        ))

    def action_init_repair(self):
        for order in self:
            if order.repair_equipment_type == 'frio_calor' and not order.stage_started:
                raise UserError(_("Debe iniciar la etapa actual presionando 'Comenzar' antes de enviar a reparación."))
            order.prev_frio_calor_stage = order.frio_calor_stage
            order.with_context(_frio_calor_stage_advance=True).frio_calor_stage = 'repair'
            order.message_post(body=_("La orden fue enviada a reparación."))

    def action_back_from_repair(self):
        for order in self:
            order.with_context(_frio_calor_stage_advance=True).frio_calor_stage = order.prev_frio_calor_stage or 'prueba_inicial'
            order.message_post(body=_("La orden volvió de reparación a su estado anterior."))

    def action_validate(self):
        for order in self:
            if order.repair_equipment_type == 'frio_calor':
                order.check_unique_repair_order()
        return super().action_validate()

    def action_send_to_pintura(self):
        for order in self:
            if order.repair_equipment_type != 'frio_calor':
                raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
            if order.frio_calor_stage != 'armado':
                raise UserError(_("Solo se puede enviar a Pintura desde la etapa 'Embolsado'."))
            if order.is_outsourced:
                raise UserError(_("No se puede modificar la etapa de una orden tercerizada."))
            if not order.stage_started:
                raise UserError(_("Debe iniciar la etapa actual presionando 'Comenzar' antes de continuar."))
            order.with_context(_frio_calor_stage_advance=True).write({'frio_calor_stage': 'pintura'})
            order.message_post(body=_("La orden fue enviada a Pintura desde Embolsado."))

    def action_back_from_pintura(self):
        for order in self:
            if order.repair_equipment_type != 'frio_calor':
                raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
            if order.frio_calor_stage != 'pintura':
                raise UserError(_("Esta acción solo aplica cuando la orden está en etapa 'Pintura'."))
            order.with_context(_revert_stage=True).write({'frio_calor_stage': 'armado'})
            order.message_post(body=_("La orden volvió de Pintura a Embolsado."))

    def action_send_to_descarte(self):
        for order in self:
            if order.frio_calor_stage in ('descarte', 'finalizado'):
                continue
            prev = order.frio_calor_stage
            order.prev_frio_calor_stage = prev
            order.with_context(
                _frio_calor_stage_advance=True,
                _descarte_action=True,
            ).write({'frio_calor_stage': 'descarte'})
            stage_name = dict(FRIO_CALOR_STAGES).get(prev, prev)
            order.message_post(body=_("La orden fue enviada a Descarte desde la etapa '%s'.", stage_name))

    def action_back_from_descarte(self):
        for order in self:
            if order.frio_calor_stage != 'descarte':
                raise UserError(_("Esta acción solo aplica a órdenes en etapa Descarte."))
            prev = order.prev_frio_calor_stage or 'prueba_inicial'
            order.with_context(_frio_calor_stage_advance=True).write({'frio_calor_stage': prev})
            order.message_post(body=_(
                "La orden volvió de Descarte a la etapa '%s'.", dict(FRIO_CALOR_STAGES).get(prev, prev)
            ))

    def action_confirm_descarte(self):
        for order in self:
            if order.frio_calor_stage != 'descarte':
                raise UserError(_("Esta acción solo aplica a órdenes en etapa Descarte."))

            # Cerrar el log de etapa activo
            now = fields.Datetime.now()
            open_log = self.env['repair.order.stage.log'].search([
                ('repair_id', '=', order.id),
                ('date_end', '=', False),
            ], limit=1)
            if open_log and open_log.date_start:
                open_log.write({'date_end': now})

            # Guardar ubicación antes de cancelar (el compute sigue disponible post-cancel)
            src_location = order.product_location_src_id

            # Cancelar la orden (unreserva stock, cambia estado a 'cancel')
            order.with_context(_descarte_action=True).action_repair_cancel()

            # Scrap del producto principal (best-effort)
            if (order.product_id and order.product_id.is_storable
                    and order.lot_id and src_location):
                try:
                    with order.env.cr.savepoint():
                        scrap = order.env['stock.scrap'].create({
                            'product_id': order.product_id.id,
                            'product_uom_id': order.product_id.uom_id.id,
                            'lot_id': order.lot_id.id,
                            'scrap_qty': order.product_qty or 1.0,
                            'location_id': src_location.id,
                            'company_id': order.company_id.id,
                            'origin': order.name,
                        })
                        scrap.action_validate()
                        order.message_post(body=_(
                            "Equipo dado de baja del stock. Registro de descarte: %s.", scrap.name
                        ))
                except Exception as e:
                    _logger.warning("Descarte scrap failed repair=%s: %s", order.name, e)
                    order.message_post(body=_(
                        "Advertencia: no se pudo dar de baja el equipo del stock automáticamente. "
                        "Verifique el stock manualmente."
                    ))

            order.message_post(body=_("Orden descartada definitivamente."))

    def action_repair_end(self):
        for order in self:
            if order.repair_equipment_type == 'frio_calor' and not order.stage_started:
                raise UserError(_("Debe iniciar la etapa actual presionando 'Comenzar' antes de finalizar."))
            order.with_context(_frio_calor_stage_advance=True).write({'frio_calor_stage': 'finalizado'})
        return super().action_repair_end()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.repair_equipment_type == 'frio_calor':
                record.check_unique_repair_order()
                self.env['repair.order.stage.log'].create({
                    'repair_id': record.id,
                    'stage': record.frio_calor_stage,
                    'user_id': self.env.context.get('_portal_user_id', self.env.user.id),
                })
        return records

    def write(self, vals):
        old_stages = {}
        if 'frio_calor_stage' in vals:
            old_stages = {
                order.id: order.frio_calor_stage
                for order in self
                if order.repair_equipment_type == 'frio_calor'
            }

        for order in self:
            # Bloqueo por tercerización
            if (order.is_outsourced
                    and not self.env.context.get('_outsource_action')
                    and not self.env.context.get('_descarte_action')):
                allowed_fields = {'is_outsourced', 'message_ids', 'message_follower_ids'}
                if not set(vals.keys()) <= allowed_fields:
                    raise UserError(_("No se puede modificar una orden tercerizada. Primero debe recibirse del tercero."))

            # Protección de frio_calor_stage contra escritura directa
            if 'frio_calor_stage' in vals and order.repair_equipment_type == 'frio_calor':
                if not self.env.context.get('_frio_calor_stage_advance') and not self.env.context.get('_revert_stage'):
                    raise UserError(_("No se puede modificar la etapa directamente. Use los botones 'Avanzar Etapa' o 'Revertir Etapa'."))

            # Validación de requires_painting
            if 'requires_painting' in vals and not vals['requires_painting']:
                if order.requires_painting and order.frio_calor_stage in ('pintura', 'armado', 'finalizado'):
                    raise ValidationError(
                        _("No se puede desmarcar 'Requiere pintura' cuando la etapa ya está en ejecución o fue superada.")
                    )

        result = super().write(vals)

        if old_stages:
            now = fields.Datetime.now()
            for order in self:
                old_stage = old_stages.get(order.id)
                if old_stage and old_stage != order.frio_calor_stage:
                    open_log = self.env['repair.order.stage.log'].search([
                        ('repair_id', '=', order.id),
                        ('date_end', '=', False),
                    ], limit=1)
                    if open_log and open_log.date_start:
                        open_log.write({'date_end': now})
                    self.env['repair.order.stage.log'].create({
                        'repair_id': order.id,
                        'stage': order.frio_calor_stage,
                        'user_id': self.env.context.get('_portal_user_id', self.env.user.id),
                    })
                    # Al salir de 'prueba_inicial' (aprobada o desaprobada) el equipo
                    # entra al flujo físico de reparación: pasar la orden a "En reparación".
                    if old_stage == 'prueba_inicial' and order.state in ('draft', 'confirmed'):
                        order.action_repair_start()

        return result

    def unlink(self):
        for order in self:
            if order.is_outsourced:
                raise UserError(_("No se puede eliminar una orden tercerizada."))
        return super().unlink()

    @api.model
    def find_repair_by_serial(self, barcode):
        # Odoo ZPL lot labels use GS1 AI "21" (serial number) prefix.
        # Try original value; if not found, strip the "21" prefix and retry.
        candidates = [barcode]
        if barcode.startswith('21') and len(barcode) > 2:
            candidates.append(barcode[2:])

        lot = None
        for candidate in candidates:
            lot = self.env['stock.lot'].search([('name', '=', candidate)], limit=1)
            if lot:
                break
        if not lot:
            return {
                'error': 'not_found',
                'message': _("No se encontró el número de serie '%s'.") % barcode,
            }

        repair = self.search(
            [('lot_id', '=', lot.id), ('state', 'not in', ['cancel', 'done'])],
            order='create_date desc',
            limit=1,
        )
        if not repair:
            repair = self.search(
                [('lot_id', '=', lot.id)],
                order='create_date desc',
                limit=1,
            )
        if not repair:
            return {
                'error': 'no_repair',
                'message': _("No se encontró una orden de reparación para el número de serie '%s'.") % barcode,
            }

        return {
            'type': 'ir.actions.act_window',
            'name': repair.name,
            'res_model': 'repair.order',
            'res_id': repair.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def check_unique_repair_order(self):
        for ro in self:
            if ro.search_count([
                ('lot_id', '=', ro.lot_id.id),
                ('state', 'not in', ['cancelled', 'done']),
            ]) > 1:
                raise UserError(_(
                    "El producto a reparar '%s' ya tiene una orden de reparación asociada en proceso para el número de serie '%s'.",
                    ro.product_id.name, ro.lot_id.name
                ))
