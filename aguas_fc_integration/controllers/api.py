# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AguasFCController(http.Controller):

    def _check_api_key(self):
        """Devuelve None si el token es válido, o el dict de error."""
        api_key = request.httprequest.headers.get('X-API-Key')
        expected_key = request.env['ir.config_parameter'].sudo().get_param('aguas_fc.api_key')
        if not api_key or api_key != expected_key:
            return {'success': False, 'error': 'Token inválido o no proporcionado'}
        return None

    def _check_required(self, data, required):
        missing = [f for f in required if not data.get(f)]
        if missing:
            return {'success': False, 'error': f'Campos requeridos faltantes: {missing}'}
        return None

    @staticmethod
    def _as_list(equipos):
        if isinstance(equipos, str):
            equipos = json.loads(equipos)
        return equipos

    # ------------------------------------------------------------------
    # Ingreso de equipos al taller (Loop -> Odoo)
    # ------------------------------------------------------------------
    @http.route(
        '/api/v1/repair/create',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def registrar_entrada(self, **kwargs):
        error = self._check_api_key()
        if error:
            return error

        data = kwargs

        required = ['fecha', 'idreparto', 'tecnico', 'usuario', 'equipos']
        error = self._check_required(data, required)
        if error:
            return error

        equipos = self._as_list(data['equipos'])

        try:
            return request.env['aguas.fc.intake'].sudo().process_entrada(
                idreparto=data['idreparto'],
                equipos=equipos,
                fecha=data['fecha'],
                tecnico=data['tecnico'],
                usuario=data['usuario'],
            )
        except Exception as e:
            _logger.exception('Error en /api/v1/repair/create')
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Salida de equipos al reparto (Loop -> Odoo)
    # ------------------------------------------------------------------
    @http.route(
        '/api/v1/salida/disponibles',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def salida_disponibles(self, **kwargs):
        error = self._check_api_key()
        if error:
            return error

        try:
            return request.env['aguas.fc.outbound'].sudo().get_disponibles(
                limite=kwargs.get('limite', 500),
                offset=kwargs.get('offset', 0),
            )
        except Exception as e:
            _logger.exception('Error en /api/v1/salida/disponibles')
            return {'success': False, 'error': str(e)}

    @http.route(
        '/api/v1/salida/validar',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def salida_validar(self, **kwargs):
        error = self._check_api_key()
        if error:
            return error

        error = self._check_required(kwargs, ['equipos'])
        if error:
            return error

        try:
            return request.env['aguas.fc.outbound'].sudo().validar_series(
                equipos=self._as_list(kwargs['equipos']),
            )
        except Exception as e:
            _logger.exception('Error en /api/v1/salida/validar')
            return {'success': False, 'error': str(e)}

    @http.route(
        '/api/v1/salida/create',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def registrar_salida(self, **kwargs):
        error = self._check_api_key()
        if error:
            return error

        data = kwargs

        required = ['fecha', 'idreparto', 'equipos']
        error = self._check_required(data, required)
        if error:
            return error

        try:
            return request.env['aguas.fc.outbound'].sudo().process_salida(
                idreparto=data['idreparto'],
                equipos=self._as_list(data['equipos']),
                fecha=data['fecha'],
                referencia_externa=data.get('referencia_externa'),
            )
        except Exception as e:
            _logger.exception('Error en /api/v1/salida/create')
            return {'success': False, 'error': str(e)}

    @http.route(
        '/api/v1/repartos/listar',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def listar_repartos(self, **kwargs):
        error = self._check_api_key()
        if error:
            return error

        try:
            return request.env['aguas.fc.outbound'].sudo().get_repartos()
        except Exception as e:
            _logger.exception('Error en /api/v1/repartos/listar')
            return {'success': False, 'error': str(e)}
