import base64

from odoo.http import Request
from odoo.tests import HttpCase, tagged

# PNG 1x1 valido
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)


@tagged('post_install', '-at_install')
class TestPortalWorkshopRotura(HttpCase):
    """Bloque P: tilde Rotura + fotos en el portal de taller."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Request_ = cls.env['maintenance.request']
        if 'x_studio_rotura' not in Request_._fields:
            # En stage/prod lo crea Studio; en una base de test lo simulamos.
            cls.env['ir.model.fields'].create({
                'name': 'x_studio_rotura',
                'model_id': cls.env['ir.model']._get('maintenance.request').id,
                'field_description': 'Rotura',
                'ttype': 'boolean',
                'state': 'manual',
            })
        cls.team = cls.env['maintenance.team'].create({
            'name': 'Taller test rotura', 'is_workshop': True,
        })
        cls.equipment = cls.env['maintenance.equipment'].create({'name': 'Equipo test rotura'})
        cls.user = cls.env['res.users'].create({
            'name': 'Portal taller rotura',
            'login': 'portal_taller_rotura',
            'password': 'portal_taller_rotura',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_portal').id,
                cls.env.ref('maintenance_portal_ivess.group_portal_workshop').id,
            ])],
        })

    def _post(self, url, data, n_photos=0, extra_files=None):
        data = dict(data, csrf_token=Request.csrf_token(self))
        files = [('rotura_photos', ('f%d.png' % i, PNG, 'image/png')) for i in range(n_photos)]
        files += extra_files or []
        return self.url_open(url, data=data, files=files or None, allow_redirects=False)

    def _photos(self, rec):
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'maintenance.request'), ('res_id', '=', rec.id),
            ('mimetype', '=like', 'image/%'),
        ])

    def _new(self, n_photos=0, rotura=True):
        self.authenticate(self.user.login, self.user.login)
        data = {
            'name': 'Orden test rotura',
            'maintenance_team_id': self.team.id,
            'equipment_id': self.equipment.id,
            'rotura_present': '1',
        }
        if rotura:
            data['rotura'] = 'on'
        res = self._post('/my/workshop/new', data, n_photos)
        rec = self.env['maintenance.request'].search(
            [('name', '=', 'Orden test rotura')], order='id desc', limit=1)
        return res, rec

    def test_create_with_rotura_and_photos(self):
        res, rec = self._new(n_photos=2)
        self.assertEqual(res.status_code, 303 if res.status_code == 303 else 302)
        self.assertTrue(rec.x_studio_rotura)
        self.assertEqual(len(self._photos(rec)), 2)
        # Quedan en el chatter de la orden
        msg = rec.message_ids.filtered(lambda m: m.attachment_ids)
        self.assertEqual(len(msg.attachment_ids), 2)

    def test_create_without_rotura_ignores_photos(self):
        _res, rec = self._new(n_photos=2, rotura=False)
        self.assertTrue(rec)
        self.assertFalse(rec.x_studio_rotura)
        self.assertFalse(self._photos(rec))

    def test_create_over_limit_creates_nothing(self):
        res, rec = self._new(n_photos=6)
        self.assertFalse(rec)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Se pueden subir hasta 5 fotos por orden (ya tiene 0)', res.text)

    def test_edit_up_to_five_then_sixth_rejected(self):
        _res, rec = self._new(n_photos=2)
        edit = {'name': rec.name, 'rotura_present': '1', 'rotura': 'on'}
        self._post(f'/my/workshop/{rec.id}/edit', edit, n_photos=3)
        self.assertEqual(len(self._photos(rec)), 5)
        res = self._post(f'/my/workshop/{rec.id}/edit', edit, n_photos=1)
        self.assertEqual(len(self._photos(rec)), 5)
        page = self.url_open(res.headers['Location'])
        self.assertIn('Se pueden subir hasta 5 fotos por orden (ya tiene 5)', page.text)

    def test_edit_over_limit_saves_nothing_from_upload(self):
        _res, rec = self._new(n_photos=4)
        self._post(f'/my/workshop/{rec.id}/edit',
                   {'name': 'Renombrada', 'rotura_present': '1', 'rotura': 'on'}, n_photos=2)
        rec.invalidate_recordset()
        self.assertEqual(rec.name, 'Renombrada')  # el resto del form si se guarda
        self.assertEqual(len(self._photos(rec)), 4)

    def test_non_image_rejected(self):
        _res, rec = self._new(n_photos=0)
        self._post(f'/my/workshop/{rec.id}/edit',
                   {'name': rec.name, 'rotura_present': '1', 'rotura': 'on'},
                   extra_files=[('rotura_photos', ('x.png', b'%PDF-1.4 no soy imagen', 'image/png'))])
        self.assertFalse(self._photos(rec))

    def test_detail_shows_rotura_badge(self):
        _res, rec = self._new(n_photos=1)
        page = self.url_open(f'/my/workshop/{rec.id}')
        self.assertIn('Rotura', page.text)
        rec.x_studio_rotura = False
        page = self.url_open(f'/my/workshop/{rec.id}')
        self.assertNotIn('text-bg-danger">\n                            <i class="fa fa-exclamation-triangle me-1"/>Rotura', page.text)
