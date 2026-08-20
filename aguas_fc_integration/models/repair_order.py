# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    def action_repair_done(self):
        res = super().action_repair_done()
        for repair in self.filtered(lambda r: r.state == 'done'):
            repair_pt = repair.company_id.aguas_fc_repair_picking_type_id
            if repair_pt and repair.picking_type_id == repair_pt:
                repair._aguas_fc_mover_a_expedicion()
        return res

    def _aguas_fc_mover_a_expedicion(self):
        """Mueve el equipo reparado de taller a expedición, ya validado.

        Se valida en el momento (antes lo hacía un cron a las 23:00) para que
        Loop vea el equipo disponible apenas termina la reparación.
        """
        self.ensure_one()
        company = self.company_id
        taller = company.aguas_fc_taller_location_id
        expedicion = company.aguas_fc_expedicion_location_id
        salida_type = company.aguas_fc_salida_picking_type_id
        product = company.aguas_fc_product_id

        if not all([taller, expedicion, salida_type, product]):
            _logger.warning(
                'Aguas FC: faltan configuraciones de salida en empresa %s — '
                'taller=%s expedicion=%s salida_type=%s product=%s',
                company.name, taller, expedicion, salida_type, product,
            )
            return

        if not self.lot_id:
            _logger.warning('Aguas FC: repair.order %s no tiene número de serie, omitiendo', self.name)
            return

        origin = f'AGUAS-FC-REPARADO-{self.name}'

        picking = self.env['stock.picking'].with_company(company).create({
            'picking_type_id': salida_type.id,
            'location_id': taller.id,
            'location_dest_id': expedicion.id,
            'origin': origin,
            'company_id': company.id,
        })

        move = self.env['stock.move'].with_company(company).create({
            'picking_id': picking.id,
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
            'location_id': taller.id,
            'location_dest_id': expedicion.id,
            'company_id': company.id,
        })

        picking.action_confirm()

        self.env['stock.move.line'].with_company(company).create({
            'picking_id': picking.id,
            'move_id': move.id,
            'product_id': product.id,
            'lot_id': self.lot_id.id,
            'quantity': 1,
            'location_id': taller.id,
            'location_dest_id': expedicion.id,
            'company_id': company.id,
        })

        picking.with_context(
            skip_sanity_check=True,
            picking_ids_not_to_backorder=picking.ids,
        ).button_validate()

        if picking.state != 'done':
            _logger.error(
                'Aguas FC: el traslado %s del serial %s quedó en estado %s; '
                'el equipo no está disponible en expedición',
                picking.name, self.lot_id.name, picking.state,
            )
            return

        _logger.info(
            'Aguas FC: serial %s disponible en expedición (%s)',
            self.lot_id.name, picking.name,
        )
