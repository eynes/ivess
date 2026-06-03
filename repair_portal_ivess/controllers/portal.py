# -*- coding: utf-8 -*-
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import UserError
from odoo.addons.quality_control_custom.models.repair_order import (
    FRIO_CALOR_STAGES,
    FRIO_CALOR_STAGE_ORDER,
    FRIO_CALOR_STAGE_ORDER_NO_PAINT,
)

_STAGE_LABELS = dict(FRIO_CALOR_STAGES)

_REPAIR_LINE_TYPE_LABELS = {
    'add': 'Agregar',
    'remove': 'Retirar',
    'recycle': 'Reciclar',
}

_REPAIR_LINE_TYPE_BADGE = {
    'add': 'success',
    'remove': 'danger',
    'recycle': 'secondary',
}

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

# Etapas a las que no se puede retroceder desde el botón Revertir del portal.
# Se llega a ellas por flujos propios ('calidad' via wizard QC, 'repair' via botón dedicado).
# Alineado con la misma restricción del backend:
#   invisible="frio_calor_stage in ('hidrolavadora', 'calidad', 'repair') or is_outsourced"
_NO_REVERT_FROM = frozenset({'hidrolavadora', 'calidad', 'repair'})


def _stage_nav_flags(repair):
    """Retorna (can_go_prev, can_go_next) según la etapa y estado actual del registro."""
    if repair.is_outsourced or repair.frio_calor_stage == 'repair':
        return False, False
    stages = FRIO_CALOR_STAGE_ORDER if repair.requires_painting else FRIO_CALOR_STAGE_ORDER_NO_PAINT
    current = repair.frio_calor_stage
    if current not in stages:
        return False, False
    idx = stages.index(current)
    can_go_prev = idx > 0 and current not in _NO_REVERT_FROM
    can_go_next = idx < len(stages) - 1
    return can_go_prev, can_go_next


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

        # Odoo ZPL encodes lot labels with GS1 AI "21" (serial number) prefix.
        # Physical scanners or unmodified camera scanners may return "21<lot_name>".
        # Build candidate list: try original value first, then without GS1 prefix.
        candidates = [barcode]
        if barcode.startswith('21') and len(barcode) > 2:
            candidates.append(barcode[2:])

        RepairOrder = request.env['repair.order'].sudo()
        repair = None
        for candidate in candidates:
            repair = RepairOrder.search([
                ('lot_id.name', '=', candidate),
                ('repair_equipment_type', '=', 'frio_calor'),
                ('state', 'not in', ['cancel', 'done']),
            ], order='create_date desc', limit=1)
            if repair:
                break

        if not repair:
            for candidate in candidates:
                repair = RepairOrder.search([
                    ('lot_id.name', '=', candidate),
                    ('repair_equipment_type', '=', 'frio_calor'),
                ], order='create_date desc', limit=1)
                if repair:
                    break

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
    def portal_repair_detail(self, repair_id, add_error=None, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.repair_equipment_type != 'frio_calor':
            return request.redirect('/my/repairs')

        can_go_prev, can_go_next = _stage_nav_flags(repair)

        parts = repair.move_ids.filtered(lambda m: m.repair_line_type)

        values = self._prepare_portal_layout_values()
        values.update({
            'repair': repair,
            'page_name': 'repair_detail',
            'stage_labels': _STAGE_LABELS,
            'stage_badge': _STAGE_BADGE,
            'can_go_prev': can_go_prev,
            'can_go_next': can_go_next,
            'parts': parts,
            'line_type_labels': _REPAIR_LINE_TYPE_LABELS,
            'line_type_badge': _REPAIR_LINE_TYPE_BADGE,
            'add_error': add_error,
        })
        return request.render('repair_portal_ivess.portal_repair_detail', values)

    @http.route(
        ['/my/repairs/<int:repair_id>/quality_approve'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_quality_approve(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.frio_calor_stage != 'calidad' or repair.is_outsourced:
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_open_advance_next_stage()
            quality_check = repair.quality_check_ids.filtered(lambda c: c.quality_state == 'none')[:1]
            if quality_check:
                quality_check.with_context(_portal_user_id=request.env.uid).do_pass()
        except (UserError, Exception):
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/quality_fail'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_quality_fail(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.frio_calor_stage != 'calidad' or repair.is_outsourced:
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_open_advance_next_stage()
            quality_check = repair.quality_check_ids.filtered(lambda c: c.quality_state == 'none')[:1]
            if quality_check:
                quality_check.with_context(_portal_user_id=request.env.uid).do_fail()
        except (UserError, Exception):
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/init_repair'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_init_repair(self, repair_id):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.frio_calor_stage == 'repair' or repair.is_outsourced:
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_init_repair()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/back_from_repair'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_back_from_repair(self, repair_id):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.frio_calor_stage != 'repair':
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_back_from_repair()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/outsource'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_outsource(self, repair_id):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.is_outsourced:
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_outsource()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/receive_from_third_party'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_receive_from_third_party(self, repair_id):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or not repair.is_outsourced:
            return request.redirect(f'/my/repairs/{repair_id}')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_receive_from_third_party()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/next_stage'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_next_stage(self, repair_id, **kw):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists():
            return request.redirect('/my/repairs')
        try:
            repair.with_context(_portal_user_id=request.env.uid).action_open_advance_next_stage()
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
            repair.with_context(_portal_user_id=request.env.uid).action_prev_frio_calor_stage()
        except UserError:
            pass
        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/<int:repair_id>/update_part_qty'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_update_part_qty(self, repair_id, **post):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.repair_equipment_type != 'frio_calor':
            return request.redirect('/my/repairs')
        if repair.is_outsourced or repair.frio_calor_stage != 'repair' or repair.state in ('done', 'cancel'):
            return request.redirect(f'/my/repairs/{repair_id}')

        try:
            move_id = int(post.get('move_id') or 0)
            quantity = float(post.get('quantity') or 0)
            if quantity < 0:
                quantity = 0.0
        except ValueError:
            return request.redirect(f'/my/repairs/{repair_id}')

        if not move_id:
            return request.redirect(f'/my/repairs/{repair_id}')

        move = request.env['stock.move'].sudo().browse(move_id)
        if not move.exists() or move.repair_id.id != repair_id:
            return request.redirect(f'/my/repairs/{repair_id}')

        try:
            with request.env.cr.savepoint():
                move.with_context(
                    _portal_user_id=request.env.uid,
                    allowed_company_ids=[repair.company_id.id],
                ).write({'quantity': quantity})
        except Exception as e:
            _logger.exception("Portal update_part_qty failed repair_id=%s move_id=%s: %s", repair_id, move_id, e)

        return request.redirect(f'/my/repairs/{repair_id}')

    @http.route(
        ['/my/repairs/products/search'],
        type='json', auth='user', website=True,
    )
    def portal_products_search(self, query=''):
        if len((query or '').strip()) < 2:
            return []
        products = request.env['product.product'].sudo().search(
            [('name', 'ilike', query.strip())],
            limit=15,
            order='name',
        )
        return [{'id': p.id, 'name': p.display_name, 'uom': p.uom_id.name} for p in products]

    @http.route(
        ['/my/repairs/<int:repair_id>/add_part'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_repair_add_part(self, repair_id, **post):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists() or repair.repair_equipment_type != 'frio_calor':
            return request.redirect('/my/repairs')
        if repair.is_outsourced or repair.frio_calor_stage != 'repair' or repair.state in ('done', 'cancel'):
            return request.redirect(f'/my/repairs/{repair_id}')

        # Validar inputs antes de tocar la BD
        try:
            repair_line_type = post.get('repair_line_type') or 'add'
            if repair_line_type not in ('add', 'remove', 'recycle'):
                repair_line_type = 'add'
            product_id = int(post.get('product_id') or 0)
            product_uom_qty = float(post.get('product_uom_qty') or 1)
            if product_uom_qty <= 0:
                product_uom_qty = 1.0
        except ValueError:
            return request.redirect(f'/my/repairs/{repair_id}?add_error=invalid_input')

        if not product_id:
            return request.redirect(f'/my/repairs/{repair_id}?add_error=no_product')

        product = request.env['product.product'].sudo().browse(product_id)
        if not product.exists():
            return request.redirect(f'/my/repairs/{repair_id}?add_error=no_product')

        # Usar savepoint para que un fallo del ORM no invalide la transacción entera.
        # allowed_company_ids garantiza que _check_company() no falle cuando el contexto
        # del portal user no incluye la empresa de la orden.
        try:
            with request.env.cr.savepoint():
                request.env['stock.move'].sudo().with_context(
                    _portal_user_id=request.env.uid,
                    allowed_company_ids=[repair.company_id.id],
                ).create({
                    'repair_id': repair_id,
                    'repair_line_type': repair_line_type,
                    'product_id': product.id,
                    'product_uom_qty': product_uom_qty,
                    'product_uom': product.uom_id.id,
                    'company_id': repair.company_id.id,
                })
        except Exception as e:
            _logger.exception("Portal add_part failed repair_id=%s: %s", repair_id, e)
            return request.redirect(f'/my/repairs/{repair_id}?add_error=create_failed')

        return request.redirect(f'/my/repairs/{repair_id}')
