# -*- coding: utf-8 -*-
import logging
import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    def action_repair_done(self):
        res = super().action_repair_done()
        for repair in self.filtered(lambda r: r.state == 'done'):
            repair_pt = repair.company_id.aguas_fc_repair_picking_type_id
            if repair_pt and repair.picking_type_id == repair_pt:
                repair._aguas_fc_agregar_a_picking_salida()
        return res

    def _aguas_fc_agregar_a_picking_salida(self):
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

        today = fields.Date.today()
        origin = f'AGUAS-FC-SALIDA-{today}'

        picking = self.env['stock.picking'].search([
            ('origin', '=', origin),
            ('state', 'not in', ['done', 'cancel']),
            ('picking_type_id', '=', salida_type.id),
            ('company_id', '=', company.id),
        ], limit=1)

        if not picking:
            picking = self.env['stock.picking'].with_company(company).create({
                'picking_type_id': salida_type.id,
                'location_id': taller.id,
                'location_dest_id': expedicion.id,
                'origin': origin,
                'company_id': company.id,
            })
            picking.action_confirm()

        move = self.env['stock.move'].with_company(company).create({
            'picking_id': picking.id,
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
            'location_id': taller.id,
            'location_dest_id': expedicion.id,
            'company_id': company.id,
        })

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

        _logger.info(
            'Aguas FC: serial %s agregado al picking de salida %s',
            self.lot_id.name, picking.name,
        )

    @api.model
    def _aguas_fc_cron_validar_salida(self):
        today = fields.Date.today()
        pickings = self.env['stock.picking'].search([
            ('origin', 'like', 'AGUAS-FC-SALIDA-%'),
            ('origin', '!=', f'AGUAS-FC-SALIDA-{today}'),
            ('state', 'not in', ['done', 'cancel']),
        ])
        for picking in pickings:
            self._aguas_fc_notificar_salida(picking)
            picking.with_context(
                skip_sanity_check=True,
                picking_ids_not_to_backorder=picking.ids,
            ).button_validate()
        _logger.info('Aguas FC: %s picking(s) de salida validados por cron', len(pickings))

    @api.model
    def _aguas_fc_notificar_salida(self, picking):
        webhook_url = self.env['ir.config_parameter'].sudo().get_param('aguas_fc.webhook_url')
        if not webhook_url:
            _logger.warning('Aguas FC: aguas_fc.webhook_url no configurado, salida no notificada')
            return

        api_key = self.env['ir.config_parameter'].sudo().get_param('aguas_fc.api_key')
        today = fields.Date.today()

        grupos = {}
        for ml in picking.move_line_ids:
            if not ml.lot_id:
                continue
            serial = ml.lot_id.name
            repair = self.env['repair.order'].search([
                ('lot_id.name', '=', serial),
                ('state', '=', 'done'),
            ], limit=1)
            idreparto = None
            if repair and repair.quality_check_id and repair.quality_check_id.picking_id:
                entrada_location = repair.quality_check_id.picking_id.location_id
                idreparto = entrada_location.aguas_idreparto
            idreparto = idreparto or 'DESCONOCIDO'
            grupos.setdefault(idreparto, []).append(serial)

        scheduled = picking.scheduled_date
        fecha = str(scheduled.date() if scheduled else today)

        for idreparto, seriales in grupos.items():
            payload = {
                'fecha': fecha,
                'idreparto': idreparto,
                'tecnico': 'SISTEMAS',
                'usuario': 'SISTEMAS',
                'equipos': seriales,
                'idubicaciondestino': 2,
                'idestadodestino': 2,
            }
            try:
                response = requests.post(
                    f'{webhook_url}/aguas/equipos/registrar-salida-camion',
                    json=payload,
                    headers={'X-API-Key': api_key},
                    timeout=30,
                )
                response.raise_for_status()
                _logger.info(
                    'Aguas FC: salida notificada para reparto=%s seriales=%s',
                    idreparto, seriales,
                )
            except Exception as e:
                _logger.error(
                    'Aguas FC: error al notificar salida reparto=%s: %s',
                    idreparto, e,
                )
