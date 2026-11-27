import base64

from odoo.exceptions import AccessError
from odoo.http import Request
from odoo.tests import HttpCase, tagged

# PNG 1x1 valido
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)


@tagged('post_install', '-at_install')
class TestPortalRoturaAccess(HttpCase):
    """Permisos del bloque P (Rotura + fotos): los controladores usan sudo(),
    la unica barrera son _check_group_workshop / _check_group_maintenance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'x_studio_rotura' not in cls.env['maintenance.request']._fields:
            # En stage/prod lo crea Studio; en una base de test lo simulamos.
            cls.env['ir.model.fields'].create({
                'name': 'x_studio_rotura',
                'model_id': cls.env['ir.model']._get('maintenance.request').id,
                'field_description': 'Rotura',
                'ttype': 'boolean',
                'state': 'manual',
            })
        cls.team = cls.env['maintenance.team'].create({
            'name': 'Taller test rotura access', 'is_workshop': True,
        })
        cls.equipment = cls.env['maintenance.equipment'].create({'name': 'Equipo test access'})
        portal = cls.env.ref('base.group_portal')
        cls.user_nogroup = cls._make_user('portal_access_nogroup', portal)
        cls.user_maint = cls._make_user(
            'portal_access_maint', portal,
            cls.env.ref('maintenance_portal_ivess.group_portal_maintenance'))
        cls.user_workshop = cls._make_user(
            'portal_access_workshop', portal,
            cls.env.ref('maintenance_portal_ivess.group_portal_workshop'))
        cls.user_both = cls._make_user(
            'portal_access_both', portal,
            cls.env.ref('maintenance_portal_ivess.group_portal_workshop'),
            cls.env.ref('maintenance_portal_ivess.group_portal_maintenance'))
        # Orden preexistente, sin rotura ni fotos
        cls.order = cls.env['maintenance.request'].create({
            'name': 'Orden access preexistente',
            'maintenance_team_id': cls.team.id,
            'equipment_id': cls.equipment.id,
        })

    @classmethod
    def _make_user(cls, login, *groups):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'password': login,
            'group_ids': [(6, 0, [g.id for g in groups])],
        })

    def _post(self, url, data, n_photos=0):
        data = dict(data, csrf_token=Request.csrf_token(self))
        files = [('rotura_photos', ('f%d.png' % i, PNG, 'image/png')) for i in range(n_photos)]
        return self.url_open(url, data=data, files=files or None, allow_redirects=False)

    def _photos(self, rec):
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'maintenance.request'), ('res_id', '=', rec.id),
        ])

    def _new_data(self, name):
        return {
            'name': name,
            'maintenance_team_id': self.team.id,
            'equipment_id': self.equipment.id,
            'rotura_present': '1',
            'rotura': 'on',
        }

    def _assert_workshop_rejected(self, user):
        self.authenticate(user.login, user.login)
        name = 'Orden access rechazada %s' % user.login
        res = self._post('/my/workshop/new', self._new_data(name), n_photos=1)
        self.assertIn(res.status_code, (302, 303))
        self.assertTrue(res.headers['Location'].endswith('/my'))
        self.assertFalse(self.env['maintenance.request'].search([('name', '=', name)]))

        res = self._post(
            f'/my/workshop/{self.order.id}/edit',
            {'name': 'Renombrada access', 'rotura_present': '1', 'rotura': 'on'},
            n_photos=1)
        self.assertIn(res.status_code, (302, 303))
        self.assertTrue(res.headers['Location'].endswith('/my'))
        self.order.invalidate_recordset()
        self.assertFalse(self.order.x_studio_rotura)
        self.assertEqual(self.order.name, 'Orden access preexistente')
        self.assertFalse(self._photos(self.order))

    def test_user_without_groups_rejected(self):
        self._assert_workshop_rejected(self.user_nogroup)

    def test_maintenance_only_user_rejected_in_workshop(self):
        self._assert_workshop_rejected(self.user_maint)

    def test_workshop_user_can_create_with_rotura_and_photo(self):
        self.authenticate(self.user_workshop.login, self.user_workshop.login)
        name = 'Orden access taller ok'
        res = self._post('/my/workshop/new', self._new_data(name), n_photos=1)
        self.assertIn(res.status_code, (302, 303))
        rec = self.env['maintenance.request'].search([('name', '=', name)])
        self.assertEqual(len(rec), 1)
        self.assertTrue(rec.x_studio_rotura)
        self.assertEqual(len(self._photos(rec)), 1)

    def test_maintenance_portal_ignores_rotura_and_photos(self):
        self.authenticate(self.user_both.login, self.user_both.login)
        res = self._post(
            f'/my/maintenance/{self.order.id}/edit',
            {'name': 'Orden access preexistente', 'rotura_present': '1', 'rotura': 'on'},
            n_photos=2)
        self.assertIn(res.status_code, (302, 303))
        self.order.invalidate_recordset()
        self.assertFalse(self.order.x_studio_rotura)
        self.assertFalse(self._photos(self.order))

    def test_model_level_acl_portal_workshop_user(self):
        """Fuera del controlador (sin sudo) el usuario de taller no tiene acceso
        directo: el unico camino a los datos es la ruta protegida por grupo."""
        order = self.order.with_user(self.user_workshop)
        with self.assertRaises(AccessError):
            order.write({'name': 'Intento directo'})
        reasons = self.env['maintenance.closure.reason'].with_user(self.user_workshop)
        with self.assertRaises(AccessError):
            reasons.create({'name': 'Intento directo'})
        self.assertEqual(self.order.name, 'Orden access preexistente')
