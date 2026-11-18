from datetime import datetime

from odoo.http import Request
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPortalWorkshopDatetime(HttpCase):
    """Bug 43: el portal guardaba schedule_date/schedule_end con la hora local
    tomada como UTC (3 h corrida en Argentina)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['maintenance.team'].create({
            'name': 'Taller test T18059',
            'is_workshop': True,
        })
        cls.equipment = cls.env['maintenance.equipment'].create({
            'name': 'Equipo test T18059',
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Portal taller T18059',
            'login': 'portal_taller_t18059',
            'password': 'portal_taller_t18059',
            'tz': 'America/Argentina/Buenos_Aires',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_portal').id,
                cls.env.ref('maintenance_portal_ivess.group_portal_workshop').id,
            ])],
        })

    def _post(self, url, data):
        data = dict(data, csrf_token=Request.csrf_token(self))
        return self.url_open(url, data=data)

    def _new_request(self, **extra):
        post = {
            'name': 'Orden test T18059',
            'maintenance_team_id': self.team.id,
            'equipment_id': self.equipment.id,
        }
        post.update(extra)
        self.authenticate(self.user.login, self.user.login)
        self._post('/my/workshop/new', post)
        return self.env['maintenance.request'].search(
            [('name', '=', 'Orden test T18059')], order='id desc', limit=1)

    def test_create_converts_local_to_utc(self):
        rec = self._new_request(
            schedule_date='2026-11-13T10:00', schedule_end='2026-11-13T12:30')
        self.assertTrue(rec)
        self.assertEqual(rec.schedule_date, datetime(2026, 11, 13, 13, 0))
        self.assertEqual(rec.schedule_end, datetime(2026, 11, 13, 15, 30))

    def test_edit_converts_and_clears(self):
        rec = self._new_request(schedule_date='2026-11-13T10:00')
        self._post(f'/my/workshop/{rec.id}/edit', {
            'name': rec.name,
            'schedule_date': '2026-11-14T08:15',
            'schedule_end': '',
        })
        rec.invalidate_recordset()
        self.assertEqual(rec.schedule_date, datetime(2026, 11, 14, 11, 15))
        self.assertFalse(rec.schedule_end)

    def test_edit_form_shows_local_time(self):
        rec = self._new_request(schedule_date='2026-11-13T10:00')
        res = self.url_open(f'/my/workshop/{rec.id}/edit')
        self.assertEqual(res.status_code, 200)
        self.assertIn('value="2026-11-13T10:00"', res.text)

    def test_detail_shows_local_time(self):
        rec = self._new_request(schedule_date='2026-11-13T10:00')
        res = self.url_open(f'/my/workshop/{rec.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn('13/11/2026 10:00', res.text)

    def test_other_timezone(self):
        self.user.tz = 'America/Mexico_City'  # UTC-6 sin DST en nov-2026
        rec = self._new_request(schedule_date='2026-11-13T10:00')
        self.assertEqual(rec.schedule_date, datetime(2026, 11, 13, 16, 0))

    def test_roundtrip_edit_without_changes_keeps_value(self):
        """Abrir el form de editar y guardar sin tocar la fecha no la mueve."""
        rec = self._new_request(schedule_date='2026-11-13T10:00')
        for _i in range(2):
            self._post(f'/my/workshop/{rec.id}/edit', {
                'name': rec.name,
                'schedule_date': '2026-11-13T10:00',
            })
        rec.invalidate_recordset()
        self.assertEqual(rec.schedule_date, datetime(2026, 11, 13, 13, 0))

    def test_invalid_format_is_ignored(self):
        rec = self._new_request(schedule_date='no-es-una-fecha')
        self.assertTrue(rec)
        self.assertFalse(rec.schedule_date)
