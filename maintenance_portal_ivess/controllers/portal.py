# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_logger = logging.getLogger(__name__)

_MAINTENANCE_PER_PAGE = 20

_MAINTENANCE_TYPE_LABELS = {
    'corrective': 'Correctivo',
    'preventive': 'Preventivo',
}

_PRIORITY_LABELS = {
    '0': 'Muy baja',
    '1': 'Baja',
    '2': 'Normal',
    '3': 'Alta',
}

_PRIORITY_BADGE = {
    '0': 'secondary',
    '1': 'info',
    '2': 'warning',
    '3': 'danger',
}

_KANBAN_STATE_LABELS = {
    'normal': 'En curso',
    'blocked': 'Bloqueado',
    'done': 'Listo para siguiente etapa',
}

_KANBAN_STATE_BADGE = {
    'normal': 'primary',
    'blocked': 'danger',
    'done': 'success',
}


class MaintenancePortalController(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'maintenance_count' in counters:
            values['maintenance_count'] = request.env['maintenance.request'].sudo().search_count([])
        return values

    @http.route(
        ['/my/maintenance', '/my/maintenance/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_my_maintenance(self, page=1, **kw):
        MaintenanceRequest = request.env['maintenance.request'].sudo()

        total = MaintenanceRequest.search_count([])
        pager = portal_pager(
            url='/my/maintenance',
            total=total,
            page=page,
            step=_MAINTENANCE_PER_PAGE,
        )
        requests = MaintenanceRequest.search(
            [],
            order='request_date desc, id desc',
            limit=_MAINTENANCE_PER_PAGE,
            offset=pager['offset'],
        )

        values = self._prepare_portal_layout_values()
        values.update({
            'maintenance_requests': requests,
            'pager': pager,
            'page_name': 'maintenance',
            'priority_labels': _PRIORITY_LABELS,
            'priority_badge': _PRIORITY_BADGE,
            'maintenance_type_labels': _MAINTENANCE_TYPE_LABELS,
        })
        return request.render('maintenance_portal_ivess.portal_my_maintenance', values)

    @http.route(
        ['/my/maintenance/<int:request_id>'],
        type='http', auth='user', website=True,
    )
    def portal_maintenance_detail(self, request_id, **kw):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/maintenance')

        values = self._prepare_portal_layout_values()
        values.update({
            'maint_request': maint_request,
            'page_name': 'maintenance_detail',
            'priority_labels': _PRIORITY_LABELS,
            'priority_badge': _PRIORITY_BADGE,
            'maintenance_type_labels': _MAINTENANCE_TYPE_LABELS,
            'kanban_state_labels': _KANBAN_STATE_LABELS,
            'kanban_state_badge': _KANBAN_STATE_BADGE,
        })
        return request.render('maintenance_portal_ivess.portal_maintenance_detail', values)
