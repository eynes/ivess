# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AguasFCIntake(models.AbstractModel):
    _name = 'aguas.fc.intake'
    _description = 'Procesador de entrada de equipos desde Aguas FC'

    @api.model
    def process_entrada(self, idreparto, equipos, fecha, tecnico, usuario):
        self = self.with_user(SUPERUSER_ID)
        src_location = self.env['stock.location'].search(
            [('aguas_idreparto', '=', str(idreparto))], limit=1
        )
        if not src_location:
            return {'success': False, 'error': f'No existe ubicación para idreparto={idreparto}'}

        company = src_location.company_id
        taller_location = company.aguas_fc_taller_location_id
        picking_type = company.aguas_fc_picking_type_id
        product = company.aguas_fc_product_id

        if not taller_location:
            raise UserError(f'No está configurada la ubicación Taller FC en la empresa {company.name}.')
        if not picking_type:
            raise UserError(f'No está configurado el tipo de operación Aguas FC en la empresa {company.name}.')
        if not product:
            raise UserError(f'No está configurado el producto Equipo FC en la empresa {company.name}.')

        lots = []
        for serial in equipos:
            lot = self.env['stock.lot'].search([
                ('name', '=', serial),
                ('product_id', '=', product.id),
            ], limit=1)
            if not lot:
                lot = self.env['stock.lot'].with_company(company).create({
                    'name': serial,
                    'product_id': product.id,
                    'company_id': company.id,
                })
            lots.append(lot)

        picking = self.env['stock.picking'].with_company(company).create({
            'picking_type_id': picking_type.id,
            'location_id': src_location.id,
            'location_dest_id': taller_location.id,
            'origin': f'AGUAS-{idreparto}-{fecha}',
            'company_id': company.id,
        })

        move = self.env['stock.move'].with_company(company).create({
            'picking_id': picking.id,
            'product_id': product.id,
            'product_uom_qty': len(lots),
            'product_uom': product.uom_id.id,
            'location_id': src_location.id,
            'location_dest_id': taller_location.id,
            'company_id': company.id,
        })

        # Confirmar antes de crear las move lines para que _action_confirm()
        # dispare _create_quality_checks() con el picking en estado draft.
        picking.action_confirm()

        for lot in lots:
            self.env['stock.move.line'].with_company(company).create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': product.id,
                'lot_id': lot.id,
                'quantity': 1,
                'location_id': src_location.id,
                'location_dest_id': taller_location.id,
                'company_id': company.id,
            })

        picking.with_context(
            skip_sanity_check=True,
            picking_ids_not_to_backorder=picking.ids,
        ).button_validate()

        _logger.info(
            'Aguas FC: picking %s creado y validado. Reparto=%s, seriales=%s',
            picking.name, idreparto, [l.name for l in lots],
        )

        return {
            'success': True,
            'picking_id': picking.id,
            'picking_name': picking.name,
            'seriales_procesados': len(lots),
        }
