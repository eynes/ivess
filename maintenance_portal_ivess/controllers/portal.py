# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime as _dt
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_logger = logging.getLogger(__name__)

_MAINTENANCE_PER_PAGE = 20
_WORKSHOP_PER_PAGE = 20

_MAINTENANCE_TYPE_LABELS = {
    'corrective': 'Correctivo',
    'preventive': 'Preventivo',
}
_MAINTENANCE_TYPE_OPTIONS = list(_MAINTENANCE_TYPE_LABELS.items())

_PRIORITY_LABELS = {
    '0': 'Muy baja',
    '1': 'Baja',
    '2': 'Normal',
    '3': 'Alta',
}
_PRIORITY_OPTIONS = list(_PRIORITY_LABELS.items())

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
_KANBAN_STATE_OPTIONS = list(_KANBAN_STATE_LABELS.items())

_KANBAN_STATE_BADGE = {
    'normal': 'primary',
    'blocked': 'danger',
    'done': 'success',
}

_MAINTENANCE_DOMAIN = [('is_internal_maintenance', '=', True)]
_WORKSHOP_DOMAIN = [('is_workshop', '=', True)]

_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(html_content):
    if not html_content:
        return ''
    return _HTML_TAG_RE.sub('', html_content).strip()


class MaintenancePortalController(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        MaintenanceRequest = request.env['maintenance.request'].sudo()
        if 'maintenance_count' in counters:
            values['maintenance_count'] = MaintenanceRequest.search_count(_MAINTENANCE_DOMAIN)
        if 'workshop_count' in counters:
            values['workshop_count'] = MaintenanceRequest.search_count(_WORKSHOP_DOMAIN)
        return values

    # ── Shared helpers ─────────────────────────────────────────────────────────

    def _maint_edit_context(self):
        """Values needed to render the edit form select controls."""
        stages = request.env['maintenance.stage'].sudo().search([], order='sequence')
        teams = request.env['maintenance.team'].sudo().search([], order='name')
        users = request.env['res.users'].sudo().search(
            [('share', '=', False), ('active', '=', True)],
            order='name', limit=200,
        )
        equipment = request.env['maintenance.equipment'].sudo().search([], order='name', limit=200)
        workcenters = request.env['mrp.workcenter'].sudo().search([], order='name', limit=100)
        return {
            'stages': stages,
            'teams': teams,
            'users': users,
            'equipment_list': equipment,
            'workcenters': workcenters,
            'maintenance_type_options': _MAINTENANCE_TYPE_OPTIONS,
            'priority_options': _PRIORITY_OPTIONS,
            'kanban_state_options': _KANBAN_STATE_OPTIONS,
            'maintenance_for_options': [('equipment', 'Equipo'), ('workcenter', 'Centro de trabajo')],
        }

    def _maint_detail_values(self, maint_request):
        """Common read-only display values for detail views."""
        return {
            'maint_request': maint_request,
            'priority_labels': _PRIORITY_LABELS,
            'priority_badge': _PRIORITY_BADGE,
            'maintenance_type_labels': _MAINTENANCE_TYPE_LABELS,
            'kanban_state_labels': _KANBAN_STATE_LABELS,
            'kanban_state_badge': _KANBAN_STATE_BADGE,
        }

    def _maint_write_from_post(self, maint_request, post):
        """Parse POST data and write to maint_request. Returns error key or None."""
        vals = {}

        name = (post.get('name') or '').strip()
        if name:
            vals['name'] = name

        if post.get('maintenance_type') in ('corrective', 'preventive'):
            vals['maintenance_type'] = post['maintenance_type']

        if post.get('priority') in ('0', '1', '2', '3'):
            vals['priority'] = post['priority']

        if post.get('kanban_state') in ('normal', 'blocked', 'done'):
            vals['kanban_state'] = post['kanban_state']

        # Optional M2O — can be cleared
        for field in ('stage_id', 'user_id', 'equipment_id'):
            raw = (post.get(field) or '').strip()
            try:
                val = int(raw) if raw else 0
                vals[field] = val if val else False
            except ValueError:
                pass

        # Required M2O — only write if a valid ID is provided
        raw = (post.get('maintenance_team_id') or '').strip()
        if raw:
            try:
                val = int(raw)
                if val:
                    vals['maintenance_team_id'] = val
            except ValueError:
                pass

        for field in ('schedule_date', 'schedule_end'):
            raw = (post.get(field) or '').strip()
            if raw:
                try:
                    vals[field] = _dt.strptime(raw, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            else:
                vals[field] = False

        desc = (post.get('description') or '').strip()
        if desc:
            if not desc.startswith('<'):
                desc = f'<p>{desc}</p>'
            vals['description'] = desc
        else:
            vals['description'] = False

        origin = (post.get('request_origin') or '').strip()
        vals['request_origin'] = origin or False

        if post.get('maintenance_for') in ('equipment', 'workcenter'):
            vals['maintenance_for'] = post['maintenance_for']

        for field in ('workcenter_id', 'production_id'):
            raw = (post.get(field) or '').strip()
            try:
                val = int(raw) if raw else 0
                vals[field] = val if val else False
            except ValueError:
                pass

        if not vals:
            return None
        try:
            with request.env.cr.savepoint():
                maint_request.write(vals)
        except Exception as e:
            _logger.exception("Portal maint write failed id=%s: %s", maint_request.id, e)
            return 'save_failed'
        return None

    def _maint_add_material(self, maint_request, post):
        """Add a material line to a maintenance.request."""
        try:
            product_id = int(post.get('product_id') or 0)
            product_uom_qty = float(post.get('product_uom_qty') or 1)
            if product_uom_qty <= 0:
                product_uom_qty = 1.0
        except (ValueError, TypeError):
            return
        if not product_id:
            return
        product = request.env['product.product'].sudo().browse(product_id)
        if not product.exists():
            return
        description = (post.get('description') or product.name or '').strip()
        try:
            with request.env.cr.savepoint():
                request.env['maintenance.request.material'].sudo().create({
                    'request_id': maint_request.id,
                    'product_id': product.id,
                    'description': description,
                    'product_uom_qty': product_uom_qty,
                    'product_uom': product.uom_id.id,
                    'company_id': maint_request.company_id.id,
                })
        except Exception as e:
            _logger.exception("Portal add_material failed request=%s: %s", maint_request.id, e)

    def _maint_delete_material(self, maint_request, material_id):
        """Delete a material line if it belongs to this request and its move isn't done."""
        material = request.env['maintenance.request.material'].sudo().browse(material_id)
        if not material.exists() or material.request_id.id != maint_request.id:
            return
        if material.stock_move_id and material.stock_move_id.state == 'done':
            return
        try:
            with request.env.cr.savepoint():
                material.unlink()
        except Exception as e:
            _logger.exception("Portal delete_material failed mat=%s: %s", material_id, e)

    # ── Órdenes de Mantenimiento  —  /my/maintenance ──────────────────────────

    @http.route(
        ['/my/maintenance', '/my/maintenance/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_my_maintenance(self, page=1, **kw):
        MaintenanceRequest = request.env['maintenance.request'].sudo()
        total = MaintenanceRequest.search_count(_MAINTENANCE_DOMAIN)
        pager = portal_pager(
            url='/my/maintenance',
            total=total,
            page=page,
            step=_MAINTENANCE_PER_PAGE,
        )
        requests_list = MaintenanceRequest.search(
            _MAINTENANCE_DOMAIN,
            order='request_date desc, id desc',
            limit=_MAINTENANCE_PER_PAGE,
            offset=pager['offset'],
        )
        values = self._prepare_portal_layout_values()
        values.update({
            'maintenance_requests': requests_list,
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
        values.update(self._maint_detail_values(maint_request))
        values.update({
            'page_name': 'maintenance_detail',
            'back_url': '/my/maintenance',
            'back_label': 'Órdenes de Mantenimiento',
            'edit_url': f'/my/maintenance/{request_id}/edit',
            'add_material_url': f'/my/maintenance/{request_id}/add_material',
            'del_material_base': f'/my/maintenance/{request_id}/delete_material',
            'product_search_url': '/my/maintenance/products/search',
        })
        return request.render('maintenance_portal_ivess.portal_maintenance_detail', values)

    @http.route(
        ['/my/maintenance/<int:request_id>/edit'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_maintenance_edit(self, request_id, **post):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/maintenance')
        if request.httprequest.method == 'POST':
            self._maint_write_from_post(maint_request, post)
            return request.redirect(f'/my/maintenance/{request_id}')
        values = self._prepare_portal_layout_values()
        values.update(self._maint_edit_context())
        values.update({
            'maint_request': maint_request,
            'page_name': 'maintenance_edit',
            'back_url': f'/my/maintenance/{request_id}',
            'back_label': 'Órdenes de Mantenimiento',
            'action_url': f'/my/maintenance/{request_id}/edit',
            'description_text': _strip_html(maint_request.description),
        })
        return request.render('maintenance_portal_ivess.portal_maintenance_edit', values)

    @http.route(
        ['/my/maintenance/<int:request_id>/add_material'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_maintenance_add_material(self, request_id, **post):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/maintenance')
        self._maint_add_material(maint_request, post)
        return request.redirect(f'/my/maintenance/{request_id}')

    @http.route(
        ['/my/maintenance/<int:request_id>/delete_material/<int:material_id>'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_maintenance_delete_material(self, request_id, material_id, **kw):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/maintenance')
        self._maint_delete_material(maint_request, material_id)
        return request.redirect(f'/my/maintenance/{request_id}')

    # ── Servicios de Taller  —  /my/workshop ─────────────────────────────────

    @http.route(
        ['/my/workshop', '/my/workshop/page/<int:page>'],
        type='http', auth='user', website=True,
    )
    def portal_my_workshops(self, page=1, **kw):
        MaintenanceRequest = request.env['maintenance.request'].sudo()
        total = MaintenanceRequest.search_count(_WORKSHOP_DOMAIN)
        pager = portal_pager(
            url='/my/workshop',
            total=total,
            page=page,
            step=_WORKSHOP_PER_PAGE,
        )
        requests_list = MaintenanceRequest.search(
            _WORKSHOP_DOMAIN,
            order='request_date desc, id desc',
            limit=_WORKSHOP_PER_PAGE,
            offset=pager['offset'],
        )
        values = self._prepare_portal_layout_values()
        values.update({
            'maintenance_requests': requests_list,
            'pager': pager,
            'page_name': 'workshops',
            'priority_labels': _PRIORITY_LABELS,
            'priority_badge': _PRIORITY_BADGE,
            'maintenance_type_labels': _MAINTENANCE_TYPE_LABELS,
        })
        return request.render('maintenance_portal_ivess.portal_my_workshops', values)

    @http.route(
        ['/my/workshop/<int:request_id>'],
        type='http', auth='user', website=True,
    )
    def portal_workshop_detail(self, request_id, **kw):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/workshop')
        values = self._prepare_portal_layout_values()
        values.update(self._maint_detail_values(maint_request))
        values.update({
            'page_name': 'workshop_detail',
            'back_url': '/my/workshop',
            'back_label': 'Servicios de Taller',
            'edit_url': f'/my/workshop/{request_id}/edit',
            'add_material_url': f'/my/workshop/{request_id}/add_material',
            'del_material_base': f'/my/workshop/{request_id}/delete_material',
            'product_search_url': '/my/maintenance/products/search',
        })
        return request.render('maintenance_portal_ivess.portal_workshop_detail', values)

    @http.route(
        ['/my/workshop/<int:request_id>/edit'],
        type='http', auth='user', website=True, methods=['GET', 'POST'],
    )
    def portal_workshop_edit(self, request_id, **post):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/workshop')
        if request.httprequest.method == 'POST':
            self._maint_write_from_post(maint_request, post)
            return request.redirect(f'/my/workshop/{request_id}')
        values = self._prepare_portal_layout_values()
        values.update(self._maint_edit_context())
        values.update({
            'maint_request': maint_request,
            'page_name': 'workshop_edit',
            'back_url': f'/my/workshop/{request_id}',
            'back_label': 'Servicios de Taller',
            'action_url': f'/my/workshop/{request_id}/edit',
            'description_text': _strip_html(maint_request.description),
        })
        return request.render('maintenance_portal_ivess.portal_workshop_edit', values)

    @http.route(
        ['/my/workshop/<int:request_id>/add_material'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_workshop_add_material(self, request_id, **post):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/workshop')
        self._maint_add_material(maint_request, post)
        return request.redirect(f'/my/workshop/{request_id}')

    @http.route(
        ['/my/workshop/<int:request_id>/delete_material/<int:material_id>'],
        type='http', auth='user', website=True, methods=['POST'],
    )
    def portal_workshop_delete_material(self, request_id, material_id, **kw):
        maint_request = request.env['maintenance.request'].sudo().browse(request_id)
        if not maint_request.exists():
            return request.redirect('/my/workshop')
        self._maint_delete_material(maint_request, material_id)
        return request.redirect(f'/my/workshop/{request_id}')

    # ── JSON: búsqueda de productos para materiales ───────────────────────────

    @http.route(
        ['/my/maintenance/products/search'],
        type='json', auth='user', website=True,
    )
    def portal_maintenance_products_search(self, query=''):
        if len((query or '').strip()) < 2:
            return []
        products = request.env['product.product'].sudo().search(
            [('name', 'ilike', query.strip()), ('type', 'in', ['consu', 'product'])],
            limit=15, order='name',
        )
        return [{'id': p.id, 'name': p.display_name, 'uom': p.uom_id.name} for p in products]

    @http.route(
        ['/my/maintenance/productions/search'],
        type='json', auth='user', website=True,
    )
    def portal_maintenance_productions_search(self, query=''):
        if len((query or '').strip()) < 2:
            return []
        productions = request.env['mrp.production'].sudo().search(
            [('name', 'ilike', query.strip()), ('state', 'not in', ['cancel'])],
            limit=15, order='id desc',
        )
        return [{'id': p.id, 'name': p.display_name} for p in productions]
