# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import UserError
from odoo.addons.quality_control_custom.models.repair_order import (
    FRIO_CALOR_STAGES,
    FRIO_CALOR_STAGE_ORDER,
    FRIO_CALOR_STAGE_ORDER_NO_PAINT,
)

_STAGE_LABELS = dict(FRIO_CALOR_STAGES)

_STAGE_BADGE = {
    'repair': 'danger',
    'calidad': 'info',
    'hidrolavadora': 'primary',
    'pileta': 'primary',
    'prueba': 'warning',
    'secado': 'warning',
    'pintura': 'secondary',
    'armado': 'success',
}

_REPAIRS_PER_PAGE = 20


def _stage_nav_flags(repair):
    """Retorna (can_go_prev, can_go_next) según la etapa y estado actual del registro."""
    if repair.is_outsourced:
        return False, False
    stages = FRIO_CALOR_STAGE_ORDER if repair.requires_painting else FRIO_CALOR_STAGE_ORDER_NO_PAINT
    current = repair.frio_calor_stage
    if current not in stages:
        return False, False
    idx = stages.index(current)
    return idx > 0, idx < len(stages) - 1


class RepairPortalController(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'repair_count' in counters:
            values['repair_count'] = request.env['repair.order'].sudo().search_count(
                [('repair_equipment_type', '=', 'frio_calor')]
            )
        return values

    @http.route(
        ['/my/repairs/scan'],
        type='http', auth='user', website=True,
    )
    def portal_repair_scan(self, barcode=None, **kw):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'repair_scan'

        if not barcode or not barcode.strip():
            return request.render('repair_portal_ivess.portal_repair_scan', values)

        barcode = barcode.strip()
        RepairOrder = request.env['repair.order'].sudo()

        repair = RepairOrder.search([
            ('lot_id.name', '=', barcode),
            ('repair_equipment_type', '=', 'frio_calor'),
            ('state', 'not in', ['cancel', 'done']),
        ], order='create_date desc', limit=1)

        if not repair:
            repair = RepairOrder.search([
                ('lot_id.name', '=', barcode),
                ('repair_equipment_type', '=', 'frio_calor'),
            ], order='create_date desc', limit=1)

        if repair:
            return request.redirect(f'/my/repairs/{repair.id}')

        values.update({'barcode': barcode, 'not_found': True})
        return request.render('repair_portal_ivess.portal_repair_scan', values)

    @http.route(
        ['/my/repairs', '/my/repairs/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_my_repairs(self, page=1, **kw):
        domain = [('repair_equipment_type', '=', 'frio_calor')]
        RepairOrder = request.env['repair.order'].sudo()

        repair_count = RepairOrder.search_count(domain)
        pager = portal_pager(
            url='/my/repairs',
            total=repair_count,
            page=page,
            step=_REPAIRS_PER_PAGE,
        )
        repairs = RepairOrder.search(
            domain,
            order='create_date desc',
            limit=_REPAIRS_PER_PAGE,
            offset=pager['offset'],
        )

        values = self._prepare_portal_layout_values()
        values.update({
            'repairs': repairs,
            'pager': pager,
            'page_name': 'repairs',
            'stage_labels': _STAGE_LABELS,
            'stage_badge': _STAGE_BADGE,
        })
        return request.render('repair_portal_ivess.portal_my_repairs', values)

    @http.route(
        ['/my/repairs/<int:repair_id>'],
        type='http', auth='user', website=True,
    )
    def portal_repair_detail(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.repair_equipment_type != 'frio_calor':
            return request.redirect('/my/repairs')

        can_go_prev, can_go_next = _stage_nav_flags(repair)

        values = self._prepare_portal_layout_values()
        values.update({
            'repair': repair,
            'page_name': 'repair_detail',
            'stage_labels': _STAGE_LABELS,
            'stage_badge': _STAGE_BADGE,
            'can_go_prev': can_go_prev,
            'can_go_next': can_go_next,
        })
        return request.render('repair_portal_ivess.portal_repair_detail', values)

    @http.route(
        ['/my/repairs/<int:repair_id>/next_stage'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_next_stage(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists():
            return request.redirect('/my/repairs')
        try:
            repair.with_context(_portal_user_id=request.uid).action_open_advance_next_stage()
        except (UserError, IndexError):
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/prev_stage'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_prev_stage(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists():
            return request.redirect('/my/repairs')
        try:
            repair.with_context(_portal_user_id=request.uid).action_prev_frio_calor_stage()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')
