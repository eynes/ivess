# -*- coding: utf-8 -*-
"""Procesador de la salida de equipos hacia el reparto (integración Loop).

Loop maneja el circuito y Odoo responde: Loop consulta qué equipos hay
disponibles en expedición, valida las series que va escaneando y avisa qué
subió al camión. El stock se mueve en el momento de la llamada.
"""
import hashlib
import logging

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AguasFCOutbound(models.AbstractModel):
    _name = 'aguas.fc.outbound'
    _description = 'Procesador de salida de equipos hacia el reparto'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_company(self, location=None):
        """Empresa que tiene la configuración de la integración."""
        if location and location.company_id:
            return location.company_id
        return self.env['res.company'].search(
            [('aguas_fc_expedicion_location_id', '!=', False)], limit=1
        )

    @api.model
    def _check_config(self, company):
        if not company:
            raise UserError('No hay ninguna empresa con la integración Aguas FC configurada.')
        if not company.aguas_fc_product_id:
            raise UserError(f'No está configurado el producto Equipo FC en la empresa {company.name}.')
        if not company.aguas_fc_expedicion_location_id:
            raise UserError(f'No está configurada la ubicación Expedición FC en la empresa {company.name}.')
        if not company.aguas_fc_salida_picking_type_id:
            raise UserError(f'No está configurado el tipo de operación Salida FC en la empresa {company.name}.')

    @api.model
    def _referencia_derivada(self, idreparto, equipos, fecha):
        """Referencia estable a partir del contenido del pedido.

        Se usa cuando Loop no manda su propio identificador: mismo reparto,
        misma fecha y mismas series dan siempre la misma referencia, de modo
        que un reintento del pedido se reconoce como repetido igual.
        """
        series = sorted((s or '').strip() for s in equipos)
        base = '%s|%s|%s' % (fecha, idreparto, ','.join(series))
        return 'AUTO-%s' % hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]

    @api.model
    def _buscar_lote(self, product, serial):
        """Busca la serie del producto configurado.

        Primero por coincidencia exacta. Si no aparece, reintenta ignorando los
        símbolos iniciales que arrastran algunas series históricas
        ("*LM57M09190009", ".242G1270133"), pero sólo acepta el resultado si hay
        una única coincidencia: nunca adivina entre varias.
        """
        serial = (serial or '').strip()
        if not serial:
            return self.env['stock.lot']
        Lot = self.env['stock.lot']
        lot = Lot.search([
            ('product_id', '=', product.id),
            ('name', '=', serial),
        ], limit=1)
        if lot:
            return lot
        candidatos = Lot.search([
            ('product_id', '=', product.id),
            ('name', 'like', serial),
        ])
        normalizados = candidatos.filtered(
            lambda l: (l.name or '').strip().lstrip('*.- ') == serial
        )
        return normalizados if len(normalizados) == 1 else Lot

    @api.model
    def _estado_serie(self, company, serial):
        """Estado de una serie: si está disponible en expedición, y si no, por qué."""
        product = company.aguas_fc_product_id
        expedicion = company.aguas_fc_expedicion_location_id
        Quant = self.env['stock.quant']

        lot = self._buscar_lote(product, serial)
        if not lot:
            return {
                'serie': serial,
                'disponible': False,
                'motivo': 'El número de serie no existe en Odoo',
            }

        en_expedicion = Quant.search([
            ('lot_id', '=', lot.id),
            ('location_id', 'child_of', expedicion.id),
            ('quantity', '>', 0),
        ], limit=1)
        if en_expedicion:
            return {
                'serie': serial,
                'serie_odoo': lot.name,
                'disponible': True,
                'ubicacion': en_expedicion.location_id.complete_name,
            }

        en_otro_lado = Quant.search([
            ('lot_id', '=', lot.id),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ], limit=1)
        if en_otro_lado:
            motivo = f'El equipo está en {en_otro_lado.location_id.complete_name}, no en expedición'
        else:
            motivo = 'El equipo no tiene stock disponible'
        return {
            'serie': serial,
            'serie_odoo': lot.name,
            'disponible': False,
            'motivo': motivo,
        }

    # ------------------------------------------------------------------
    # S1 — Equipos disponibles para subir al camión
    # ------------------------------------------------------------------
    @api.model
    def get_disponibles(self, limite=500, offset=0):
        self = self.with_user(SUPERUSER_ID)
        company = self._get_company()
        self._check_config(company)

        try:
            limite = min(int(limite or 500), 1000)
            offset = max(int(offset or 0), 0)
        except (TypeError, ValueError):
            return {'success': False, 'error': 'Los parámetros limite y offset deben ser numéricos'}

        product = company.aguas_fc_product_id
        expedicion = company.aguas_fc_expedicion_location_id
        domain = [
            ('location_id', 'child_of', expedicion.id),
            ('product_id', '=', product.id),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
        ]
        Quant = self.env['stock.quant']
        total = Quant.search_count(domain)
        quants = Quant.search(domain, limit=limite, offset=offset, order='id')

        return {
            'success': True,
            'total': total,
            'devueltos': len(quants),
            'offset': offset,
            'equipos': [{
                'serie': quant.lot_id.name,
                'producto': product.display_name,
                'ubicacion': quant.location_id.complete_name,
                'fecha_disponible': str(quant.in_date.date()) if quant.in_date else False,
            } for quant in quants],
        }

    # ------------------------------------------------------------------
    # S2 — Validar las series escaneadas
    # ------------------------------------------------------------------
    @api.model
    def validar_series(self, equipos):
        self = self.with_user(SUPERUSER_ID)
        company = self._get_company()
        self._check_config(company)
        return {
            'success': True,
            'equipos': [self._estado_serie(company, serial) for serial in equipos],
        }

    # ------------------------------------------------------------------
    # S3 — Registrar la carga al reparto (mueve el stock en el momento)
    # ------------------------------------------------------------------
    @api.model
    def process_salida(self, idreparto, equipos, fecha, referencia_externa=None):
        self = self.with_user(SUPERUSER_ID)

        dest_location = self.env['stock.location'].search(
            [('aguas_idreparto', '=', str(idreparto))], limit=1
        )
        if not dest_location:
            return {'success': False, 'error': f'No existe ubicación para idreparto={idreparto}'}

        company = self._get_company(dest_location)
        self._check_config(company)

        # referencia_externa es opcional: si Loop no manda la suya, se deriva del
        # contenido del pedido para no perder la proteccion contra reintentos.
        if not referencia_externa:
            referencia_externa = self._referencia_derivada(idreparto, equipos, fecha)

        # Idempotencia: si Loop reintenta el mismo pedido no se duplica el stock.
        anterior = self.env['stock.picking'].search(
            [('aguas_fc_ref_externa', '=', referencia_externa)], limit=1
        )
        if anterior:
            _logger.info(
                'Aguas FC: referencia %s ya registrada en %s, no se duplica',
                referencia_externa, anterior.name,
            )
            return {
                'success': True,
                'ya_registrado': True,
                'picking_id': anterior.id,
                'picking_name': anterior.name,
                'seriales_procesados': len(anterior.move_line_ids),
                'origin': anterior.origin,
                'referencia_externa': referencia_externa,
            }

        product = company.aguas_fc_product_id
        expedicion = company.aguas_fc_expedicion_location_id
        salida_type = company.aguas_fc_salida_picking_type_id

        # Validación previa: todo o nada.
        lots = []
        errores = []
        ya_pedidos = set()
        for serial in equipos:
            estado = self._estado_serie(company, serial)
            if not estado.get('disponible'):
                errores.append({'serie': serial, 'motivo': estado.get('motivo')})
                continue
            lot = self._buscar_lote(product, serial)
            if lot.id in ya_pedidos:
                errores.append({'serie': serial, 'motivo': 'La serie viene repetida en el pedido'})
                continue
            ya_pedidos.add(lot.id)
            lots.append(lot)

        if errores:
            return {
                'success': False,
                'error': 'Hay equipos no disponibles',
                'detalle': errores,
            }

        origin = f'LOOP-{idreparto}-{fecha}'
        picking = self.env['stock.picking'].with_company(company).create({
            'picking_type_id': salida_type.id,
            'location_id': expedicion.id,
            'location_dest_id': dest_location.id,
            'origin': origin,
            'aguas_fc_ref_externa': referencia_externa,
            'company_id': company.id,
        })

        move = self.env['stock.move'].with_company(company).create({
            'picking_id': picking.id,
            'product_id': product.id,
            'product_uom_qty': len(lots),
            'product_uom': product.uom_id.id,
            'location_id': expedicion.id,
            'location_dest_id': dest_location.id,
            'company_id': company.id,
        })

        picking.action_confirm()

        for lot in lots:
            self.env['stock.move.line'].with_company(company).create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': product.id,
                'lot_id': lot.id,
                'quantity': 1,
                'location_id': expedicion.id,
                'location_dest_id': dest_location.id,
                'company_id': company.id,
            })

        picking.with_context(
            skip_sanity_check=True,
            picking_ids_not_to_backorder=picking.ids,
        ).button_validate()

        if picking.state != 'done':
            raise UserError(
                f'El traslado {picking.name} quedó en estado {picking.state} en lugar de Hecho.'
            )

        _logger.info(
            'Aguas FC: salida %s validada. Reparto=%s, seriales=%s',
            picking.name, idreparto, [l.name for l in lots],
        )

        return {
            'success': True,
            'ya_registrado': False,
            'picking_id': picking.id,
            'picking_name': picking.name,
            'seriales_procesados': len(lots),
            'origin': origin,
            'referencia_externa': referencia_externa,
        }

    # ------------------------------------------------------------------
    # S4 — Repartos con ID cargado
    # ------------------------------------------------------------------
    @api.model
    def get_repartos(self):
        self = self.with_user(SUPERUSER_ID)
        ubicaciones = self.env['stock.location'].search(
            [('aguas_idreparto', '!=', False)], order='complete_name'
        )
        return {
            'success': True,
            'repartos': [{
                'idreparto': ubicacion.aguas_idreparto,
                'ubicacion': ubicacion.complete_name,
            } for ubicacion in ubicaciones],
        }
