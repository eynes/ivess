# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSessionInfo(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        cls.c1 = Company.create({"name": "CGS S1"})
        cls.c2 = Company.create({"name": "CGS S2"})
        cls.c3 = Company.create({"name": "CGS S3"})
        cls.group = cls.env["res.company.group"].create(
            {"name": "CGS S grupo", "company_ids": [(6, 0, (cls.c1 | cls.c2).ids)]}
        )
        cls.locked = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "CGS S bloqueado",
                    "login": "cgs_s_locked",
                    "password": "cgs_s_locked",
                    "company_id": cls.c1.id,
                    "company_ids": [(6, 0, (cls.c1 | cls.c2 | cls.c3).ids)],
                    "can_switch_company": False,
                    "assigned_company_group_id": cls.group.id,
                    "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
                }
            )
        )

    def _session_info(self):
        self.authenticate("cgs_s_locked", "cgs_s_locked")
        response = self.url_open(
            "/web/session/get_session_info",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()["result"]

    def test_session_info_exposes_lock_without_trimming_companies(self):
        info = self._session_info()
        self.assertEqual(
            sorted(info["company_locked_ids"]), sorted(self.group.company_ids.ids)
        )
        self.assertEqual(
            info["user_companies"]["current_company"], info["company_locked_ids"][0]
        )
        # otros módulos indexan allowed_companies por cada empresa del usuario:
        # no se debe recortar (regresión: KeyError en hr_timesheet.session_info)
        allowed = {int(cid) for cid in info["user_companies"]["allowed_companies"]}
        self.assertTrue(set(self.locked.company_ids.ids) <= allowed)
