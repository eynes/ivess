# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .repair_order import FRIO_CALOR_STAGES

_logger = logging.getLogger(__name__)

# Etapas habilitadas para el procesamiento por lote.
BATCH_ALLOWED_STAGES = frozenset({'hidrolavadora', 'pintura'})


class RepairBatch(models.Model):
    _name = 'repair.batch'
    _inherit = ['mail.thread']
    _description = 'Lote de Procesamiento de Reparaciones'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia', required=True, copy=False, readonly=True,
        default=lambda self: _('Nuevo'),
    )
    stage = fields.Selection(
        selection=FRIO_CALOR_STAGES,
        string='Etapa',
        readonly=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'En Preparación'),
            ('in_progress', 'En Proceso'),
            ('done', 'Finalizado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    repair_ids = fields.Many2many(
        'repair.order',
        'repair_batch_repair_order_rel',
        'batch_id',
        'repair_id',
        string='Equipos',
        copy=False,
    )
    repair_count = fields.Integer(string='Cantidad de Equipos', compute='_compute_repair_count')
    user_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.context.get('_portal_user_id', self.env.user.id),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    date_start = fields.Datetime(string='Inicio', readonly=True)
    date_end = fields.Datetime(string='Fin', readonly=True)

    @api.depends('repair_ids')
    def _compute_repair_count(self):
        for batch in self:
            batch.repair_count = len(batch.repair_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('repair.batch') or _('Nuevo')
        return super().create(vals_list)

    def unlink(self):
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_("Solo se pueden eliminar lotes en preparación."))
        return super().unlink()

    def _check_can_add(self, repair):
        """Retorna un mensaje (str) si 'repair' no puede agregarse a este lote, o None si es válido."""
        self.ensure_one()
        if self.state != 'draft':
            return _("Solo se pueden agregar equipos a un lote en preparación.")
        if repair in self.repair_ids:
            return _("El equipo ya forma parte de este lote.")
        if repair.repair_equipment_type != 'frio_calor':
            return _("No es un equipo de tipo Frío/Calor.")
        if repair.state in ('draft', 'cancel', 'done'):
            return _("La orden no está en un estado válido para procesar.")
        if repair.is_outsourced:
            return _("El equipo está tercerizado.")
        if repair.frio_calor_stage not in BATCH_ALLOWED_STAGES:
            stage_label = dict(FRIO_CALOR_STAGES).get(repair.frio_calor_stage, repair.frio_calor_stage)
            return _("Etapa actual '%s' no habilitada para procesamiento por lote.", stage_label)
        if repair.stage_started:
            return _("El equipo ya tiene la etapa iniciada individualmente; no puede agregarse a un lote.")
        if self.stage and repair.frio_calor_stage != self.stage:
            repair_stage_label = dict(FRIO_CALOR_STAGES).get(repair.frio_calor_stage, repair.frio_calor_stage)
            batch_stage_label = dict(FRIO_CALOR_STAGES).get(self.stage, self.stage)
            return _(
                "El equipo está en la etapa '%s', distinta a la del lote ('%s').",
                repair_stage_label, batch_stage_label,
            )
        other_batch = self.search([
            ('id', '!=', self.id),
            ('state', '!=', 'done'),
            ('repair_ids', '=', repair.id),
        ], limit=1)
        if other_batch:
            return _("El equipo ya forma parte del lote activo '%s'.", other_batch.name)
        return None

    def action_add_repair(self, repair):
        self.ensure_one()
        error = self._check_can_add(repair)
        if error:
            raise UserError(error)
        if not self.stage:
            self.stage = repair.frio_calor_stage
        self.write({'repair_ids': [(4, repair.id)]})
        self.message_post(body=_("Equipo '%s' agregado al lote.", repair.name))

    def action_remove_repair(self, repair):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Solo se pueden quitar equipos de un lote en preparación."))
        self.write({'repair_ids': [(3, repair.id)]})
        self.message_post(body=_("Equipo '%s' quitado del lote.", repair.name))
        if not self.repair_ids:
            self.stage = False

    def action_start(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("El lote ya fue iniciado."))
        if not self.repair_ids:
            raise UserError(_("El lote no tiene equipos cargados."))

        errors = []
        for repair in self.repair_ids:
            if repair.stage_started:
                errors.append(_("%s: la etapa ya estaba iniciada.", repair.name))
                continue
            try:
                with self.env.cr.savepoint():
                    repair.action_start_current_stage()
            except UserError as e:
                errors.append(_("%s: %s", repair.name, str(e)))
            except Exception as e:
                _logger.exception("Batch start failed repair_id=%s batch=%s: %s", repair.id, self.name, e)
                errors.append(_("%s: ocurrió un error inesperado.", repair.name))

        self.write({'state': 'in_progress', 'date_start': fields.Datetime.now()})
        if errors:
            self.message_post(body=_("Lote iniciado con incidencias:<br/>%s", '<br/>'.join(errors)))
        else:
            self.message_post(
                body=_("Lote iniciado. Se comenzó el conteo de tiempo de %s equipo(s).", len(self.repair_ids))
            )

    def action_finish(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("El lote no está en proceso."))

        errors = []
        for repair in self.repair_ids:
            if not repair.stage_started:
                errors.append(_("%s: debe iniciar la etapa antes de finalizar.", repair.name))
                continue
            try:
                with self.env.cr.savepoint():
                    order = repair.with_context(_batch_processing=True)
                    if self.stage == 'hidrolavadora':
                        order.action_open_advance_next_stage()
                    elif self.stage == 'pintura':
                        order.action_back_from_pintura()
            except (UserError, IndexError) as e:
                errors.append(_("%s: %s", repair.name, str(e)))
            except Exception as e:
                _logger.exception("Batch finish failed repair_id=%s batch=%s: %s", repair.id, self.name, e)
                errors.append(_("%s: ocurrió un error inesperado.", repair.name))

        self.write({'state': 'done', 'date_end': fields.Datetime.now()})
        if errors:
            self.message_post(body=_("Lote finalizado con incidencias:<br/>%s", '<br/>'.join(errors)))
        else:
            self.message_post(
                body=_("Lote finalizado. %s equipo(s) avanzaron de etapa.", len(self.repair_ids))
            )
