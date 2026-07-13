# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AguasFCController(http.Controller):

    @http.route(
        '/api/v1/repair/create',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def registrar_entrada(self, **kwargs):
        api_key = request.httprequest.headers.get('X-API-Key')
        expected_key = request.env['ir.config_parameter'].sudo().get_param('aguas_fc.api_key')
        if not api_key or api_key != expected_key:
            return {'success': False, 'error': 'Token inválido o no proporcionado'}

        data = kwargs

        required = ['fecha', 'idreparto', 'tecnico', 'usuario', 'equipos']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return {'success': False, 'error': f'Campos requeridos faltantes: {missing}'}

        equipos = data['equipos']
        if isinstance(equipos, str):
            equipos = json.loads(equipos)

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
