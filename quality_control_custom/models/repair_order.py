# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


FRIO_CALOR_STAGES = [
    ('hidrolavadora', 'Limpieza con hidrolavadora'),
    ('pileta', 'Lavado en pileta'),
    ('prueba', 'Prueba y sanitización'),
    ('secado', 'Secado'),
    ('pintura', 'Pintura'),
    ('armado', 'Armado'),
]

FRIO_CALOR_STAGE_ORDER = [s[0] for s in FRIO_CALOR_STAGES]
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
        default='hidrolavadora',
        tracking=True,
    )

    requires_painting = fields.Boolean(
        string="Requiere pintura",
        default=False,
    )

    is_outsourced = fields.Boolean(
        string="Terciarizado",
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
        string="Traslado de Terciarización",
        readonly=True,
        copy=False,
    )

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
                raise UserError(_("No se puede avanzar la etapa de una orden terciarizada."))
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
                raise UserError(_("No se puede revertir la etapa de una orden terciarizada."))
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

    def action_open_advance_stage_wizard(self):
        self.ensure_one()
        if self.repair_equipment_type != 'frio_calor':
            raise UserError(_("Esta acción solo aplica a equipos de tipo Frío/Calor."))
        if self.is_outsourced:
            raise UserError(_("No se puede avanzar la etapa de una orden terciarizada."))
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
            raise UserError(_("No se puede revertir la etapa de una orden terciarizada."))
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
        for order in self:
            stage_label = dict(FRIO_CALOR_STAGES).get(order.frio_calor_stage, order.frio_calor_stage)

            internal_picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('company_id', 'in', [order.company_id.id, False]),
            ], limit=1)
            if not internal_picking_type:
                raise UserError(_("No se encontró un tipo de operación de traslado interno."))

            dest_location = order.company_id.terciarizacion_location_id
            if not dest_location:
                raise UserError(_(
                    "No se configuró la ubicación de terciarización para la empresa '%s'. "
                    "Configúrela en la ficha de la empresa."
                ) % order.company_id.name)

            source_location = order.location_id or internal_picking_type.default_location_src_id
            move_vals = {
                'product_id': order.product_id.id,
                'product_uom_qty': order.product_qty,
                'product_uom': order.product_uom.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            }
            picking = self.env['stock.picking'].create({
                'picking_type_id': internal_picking_type.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'origin': _("Terciarización etapa: %s - %s - %s") % (stage_label, order.name, dest_location.display_name),
                'move_ids': [(0, 0, move_vals)],
            })
            picking.action_confirm()

            order.with_context(_outsource_action=True).write({
                'is_outsourced': True,
                'outsource_transfer_id': picking.id,
            })
            order.message_post(
                body=_("La orden fue terciarizada desde la etapa '%s'. Se generó el traslado %s hacia %s.", stage_label, picking.name, dest_location.display_name),
            )

    def action_receive_from_third_party(self):
        for order in self:
            order.with_context(
                _outsource_action=True,
                _frio_calor_stage_advance=True,
            ).write({
                'is_outsourced': False,
                'frio_calor_stage': 'hidrolavadora',
            })
            order.message_post(body=_("La orden fue recibida del tercero. Etapa reiniciada a 'Limpieza con hidrolavadora'."))

    def write(self, vals):
        for order in self:
            # Bloqueo por terciarización
            if order.is_outsourced and not self.env.context.get('_outsource_action'):
                allowed_fields = {'is_outsourced', 'message_ids', 'message_follower_ids'}
                if not set(vals.keys()) <= allowed_fields:
                    raise UserError(_("No se puede modificar una orden terciarizada. Primero debe recibirse del tercero."))

            # Protección de frio_calor_stage contra escritura directa
            if 'frio_calor_stage' in vals and order.repair_equipment_type == 'frio_calor':
                if not self.env.context.get('_frio_calor_stage_advance') and not self.env.context.get('_revert_stage'):
                    raise UserError(_("No se puede modificar la etapa directamente. Use los botones 'Avanzar Etapa' o 'Revertir Etapa'."))

            # Validación de requires_painting
            if 'requires_painting' in vals and not vals['requires_painting']:
                if order.requires_painting and order.frio_calor_stage in ('pintura', 'armado'):
                    raise ValidationError(
                        _("No se puede desmarcar 'Requiere pintura' cuando la etapa ya está en ejecución o fue superada.")
                    )

        return super().write(vals)

    def unlink(self):
        for order in self:
            if order.is_outsourced:
                raise UserError(_("No se puede eliminar una orden terciarizada."))
        return super().unlink()
