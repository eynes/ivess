# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'aguas_fc_integration')
class TestSalidaAnular(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Equipo FC test',
            'is_storable': True,
            'tracking': 'serial',
        })
        warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.expedicion = cls.env['stock.location'].create({
            'name': 'Expedicion FC test',
            'usage': 'internal',
            'location_id': warehouse.view_location_id.id,
        })
        cls.reparto = cls.env['stock.location'].create({
            'name': 'Reparto test',
            'usage': 'internal',
            'location_id': warehouse.view_location_id.id,
            'aguas_idreparto': 'TEST-99',
        })
        # Como en producción: la carga asigna las series a mano, sin reserva automática.
        warehouse.int_type_id.reservation_method = 'manual'
        cls.company.write({
            'aguas_fc_product_id': cls.product.id,
            'aguas_fc_expedicion_location_id': cls.expedicion.id,
            'aguas_fc_salida_picking_type_id': warehouse.int_type_id.id,
        })
        cls.lots = cls.env['stock.lot']
        for name in ('FCT-001', 'FCT-002', 'FCT-003'):
            lot = cls.env['stock.lot'].create({
                'name': name,
                'product_id': cls.product.id,
                'company_id': cls.company.id,
            })
            cls.env['stock.quant']._update_available_quantity(
                cls.product, cls.expedicion, 1, lot_id=lot)
            cls.lots |= lot
        cls.Outbound = cls.env['aguas.fc.outbound']

    def _cargar(self, series, ref='REF-1'):
        res = self.Outbound.process_salida(
            idreparto='TEST-99', equipos=series, fecha='2026-10-30',
            referencia_externa=ref)
        self.assertTrue(res['success'], res)
        return self.env['stock.picking'].browse(res['picking_id'])

    def _donde(self, serie):
        quant = self.env['stock.quant'].search([
            ('lot_id.name', '=', serie), ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ])
        return quant.location_id

    def test_anular_devuelve_stock_y_libera_referencia(self):
        original = self._cargar(['FCT-001', 'FCT-002'])
        self.assertEqual(self._donde('FCT-001'), self.reparto)

        res = self.Outbound.anular_salida('REF-1')
        self.assertTrue(res['success'], res)
        self.assertFalse(res['ya_anulado'])
        self.assertEqual(res['seriales_anulados'], 2)

        self.assertEqual(self._donde('FCT-001'), self.expedicion)
        self.assertEqual(self._donde('FCT-002'), self.expedicion)
        devolucion = original.aguas_fc_anulacion_id
        self.assertEqual(devolucion.state, 'done')
        self.assertEqual(devolucion.return_id, original)
        self.assertEqual(devolucion.location_id, self.reparto)
        self.assertEqual(devolucion.location_dest_id, self.expedicion)
        self.assertEqual(
            devolucion.move_ids.origin_returned_move_id, original.move_ids)
        self.assertFalse(original.aguas_fc_ref_externa)
        self.assertEqual(original.aguas_fc_ref_externa_anulada, 'REF-1')

    def test_anular_reintento_es_idempotente(self):
        self._cargar(['FCT-001'])
        self.Outbound.anular_salida('REF-1')
        res = self.Outbound.anular_salida('REF-1')
        self.assertTrue(res['success'])
        self.assertTrue(res['ya_anulado'])
        self.assertEqual(self.env['stock.picking'].search_count(
            [('return_id', '!=', False), ('origin', 'like', 'Anulación')]), 1)

    def test_anular_referencia_inexistente(self):
        res = self.Outbound.anular_salida('NO-EXISTE')
        self.assertFalse(res['success'])

    def test_anular_serie_fuera_del_reparto_no_mueve_nada(self):
        original = self._cargar(['FCT-001', 'FCT-002'])
        # FCT-002 ya no está en el reparto.
        lot = self.lots.filtered(lambda l: l.name == 'FCT-002')
        self.env['stock.quant']._update_available_quantity(
            self.product, self.reparto, -1, lot_id=lot)
        res = self.Outbound.anular_salida('REF-1')
        self.assertFalse(res['success'])
        self.assertEqual(res['detalle'][0]['serie'], 'FCT-002')
        self.assertEqual(self._donde('FCT-001'), self.reparto)
        self.assertEqual(original.aguas_fc_ref_externa, 'REF-1')
        self.assertFalse(original.aguas_fc_anulacion_id)

    def test_anular_serie_reservada_no_mueve_nada(self):
        original = self._cargar(['FCT-001'])
        lot = self.lots.filtered(lambda l: l.name == 'FCT-001')
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot.id), ('location_id', '=', self.reparto.id)])
        quant.reserved_quantity = 1
        res = self.Outbound.anular_salida('REF-1')
        self.assertFalse(res['success'])
        self.assertIn('reservada', res['detalle'][0]['motivo'])
        self.assertEqual(original.aguas_fc_ref_externa, 'REF-1')

    def test_reemplazar_mismo_reparto_y_misma_referencia(self):
        original = self._cargar(['FCT-001', 'FCT-002'])
        res = self.Outbound.reemplazar_salida('REF-1', ['FCT-001', 'FCT-003'])
        self.assertTrue(res['success'], res)
        self.assertFalse(res['ya_registrado'])
        nueva = self.env['stock.picking'].browse(res['picking_id'])
        self.assertEqual(nueva.aguas_fc_ref_externa, 'REF-1')
        self.assertEqual(nueva.location_dest_id, self.reparto)
        self.assertEqual(original.aguas_fc_reemplazo_id, nueva)
        self.assertEqual(self._donde('FCT-001'), self.reparto)
        self.assertEqual(self._donde('FCT-002'), self.expedicion)
        self.assertEqual(self._donde('FCT-003'), self.reparto)

    def test_reemplazar_reintento_responde_ya_registrado(self):
        self._cargar(['FCT-001'])
        primero = self.Outbound.reemplazar_salida('REF-1', ['FCT-002'])
        res = self.Outbound.reemplazar_salida('REF-1', ['FCT-002'])
        self.assertTrue(res['success'])
        self.assertTrue(res['ya_registrado'])
        self.assertEqual(res['picking_id'], primero['picking_id'])

    def test_reemplazar_con_serie_invalida_deja_la_original_intacta(self):
        original = self._cargar(['FCT-001'])
        res = self.Outbound.reemplazar_salida('REF-1', ['FCT-001', 'NO-EXISTE'])
        self.assertFalse(res['success'])
        self.assertEqual(original.aguas_fc_ref_externa, 'REF-1')
        self.assertFalse(original.aguas_fc_anulacion_id)
        self.assertEqual(self._donde('FCT-001'), self.reparto)
