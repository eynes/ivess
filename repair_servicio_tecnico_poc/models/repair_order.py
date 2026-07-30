# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    def action_repair_start(self):
        res = super().action_repair_start()
        self.filtered(
            lambda o: o.sale_order_id and o.repair_equipment_type == 'frio_calor'
        )._poc_unlock_frio_calor_stage()
        return res

    def _poc_unlock_frio_calor_stage(self):
        """Satisface 'stage_started' del pipeline de quality_control_custom para que
        action_repair_end() no bloquee el cierre de órdenes de servicio técnico
        (vinculadas a una venta) que nunca van a recorrer las etapas de taller
        Frío/Calor. No se reescribe ni se saltea la lógica de quality_control_custom:
        solo se completa el dato (date_start) que su propio código espera encontrar.
        """
        for order in self:
            open_log = order.stage_log_ids.filtered(lambda l: not l.date_end and not l.date_start)
            if open_log:
                open_log[0].date_start = fields.Datetime.now()

    @api.model
    def poc_create_test_field_service_order(self):
        """Genera de punta a punta un caso de prueba (producto F/C con N° de
        serie, venta del servicio técnico confirmada y la orden de reparación
        vinculada, en borrador) para poder recorrer el flujo a mano desde la UI:
        Confirmar -> Iniciar reparación -> agregar piezas -> Reparado.

        Solo existe para este módulo de prueba; no forma parte del alcance
        pedido, es una ayuda para no tener que armar todo manualmente cada vez.
        """
        company = self.env.company

        repair_type = self.env['stock.picking.type'].search([
            ('code', '=', 'repair_operation'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not repair_type:
            raise UserError(_(
                "No hay un tipo de operación de reparación (code='repair_operation') "
                "configurado para la empresa %s. Es un prerrequisito nativo del módulo "
                "'repair', no algo que deba resolver este módulo de prueba.",
                company.name,
            ))

        product = self.env['product.product'].search([
            ('default_code', '=', 'POC-FC-EQUIPO'),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        if not product:
            product = self.env['product.product'].create({
                'name': 'Equipo Frío/Calor (POC)',
                'default_code': 'POC-FC-EQUIPO',
                'type': 'consu',
                'is_storable': True,
                'tracking': 'serial',
                'repair_equipment_type': 'frio_calor',
            })

        lot = self.env['stock.lot'].create({
            'product_id': product.id,
            'name': 'POC-SN-%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S%f'),
            'company_id': company.id,
        })

        service_product = self.env['product.product'].search([
            ('default_code', '=', 'POC-FC-SERVICIO'),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        if not service_product:
            service_product = self.env['product.product'].create({
                'name': 'Servicio Técnico F/C a domicilio (POC)',
                'default_code': 'POC-FC-SERVICIO',
                'type': 'service',
            })

        partner = self.env['res.partner'].search([('customer_rank', '>', 0)], limit=1) \
            or self.env['res.partner'].search([], limit=1)

        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'company_id': company.id,
            'order_line': [(0, 0, {
                'product_id': service_product.id,
                'product_uom_qty': 1,
            })],
        })
        sale_order.action_confirm()

        repair = self.create({
            'product_id': product.id,
            'lot_id': lot.id,
            'company_id': company.id,
            'picking_type_id': repair_type.id,
            'partner_id': partner.id,
            'sale_order_id': sale_order.id,
            'sale_order_line_id': sale_order.order_line[0].id,
        })

        # Deja una cantidad disponible en la ubicación de origen del producto para
        # que "Confirmar" no dispare el wizard nativo de cantidad insuficiente:
        # eso es ruido del flujo estándar de stock, no algo que este POC necesite probar.
        self.env['stock.quant']._update_available_quantity(
            product, repair.product_location_src_id, 1.0, lot_id=lot,
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order',
            'res_id': repair.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
