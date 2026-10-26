# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCompanyGroup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        cls.c1 = Company.create({"name": "CGS Empresa 1"})
        cls.c2 = Company.create({"name": "CGS Empresa 2"})
        cls.c3 = Company.create({"name": "CGS Empresa 3"})
        cls.group = cls.env["res.company.group"].create(
            {"name": "CGS Grupo 1+2", "company_ids": [(6, 0, (cls.c1 | cls.c2).ids)]}
        )
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.free_user = Users.create(
            {
                "name": "CGS libre",
                "login": "cgs_free",
                "company_id": cls.c1.id,
                "company_ids": [(6, 0, (cls.c1 | cls.c2 | cls.c3).ids)],
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.partial_user = Users.create(
            {
                "name": "CGS parcial",
                "login": "cgs_partial",
                "company_id": cls.c1.id,
                "company_ids": [(6, 0, (cls.c1 | cls.c3).ids)],
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.locked_user = Users.create(
            {
                "name": "CGS bloqueado",
                "login": "cgs_locked",
                "company_id": cls.c1.id,
                "company_ids": [(6, 0, (cls.c1 | cls.c2 | cls.c3).ids)],
                "can_switch_company": False,
                "assigned_company_group_id": cls.group.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _env(self, user, allowed=None):
        ctx = {"allowed_company_ids": allowed} if allowed else {}
        return self.env(user=user, context=ctx)

    # --- Oferta de grupos --------------------------------------------------
    def test_group_offered_only_with_full_access(self):
        Group = self.env["res.company.group"]
        self.assertIn(self.group, Group._get_available_for_user(self.free_user))
        self.assertNotIn(self.group, Group._get_available_for_user(self.partial_user))

    def test_group_stops_being_offered_when_access_removed(self):
        self.free_user.company_ids = [(3, self.c2.id)]
        self.assertNotIn(
            self.group,
            self.env["res.company.group"]._get_available_for_user(self.free_user),
        )

    def test_session_info_payload(self):
        info = self.free_user._get_company_switcher_info()
        self.assertEqual(info["company_locked_ids"], False)
        self.assertEqual(
            [g["company_ids"] for g in info["company_groups"]],
            [self.group.company_ids.ids],
        )
        locked = self.locked_user._get_company_switcher_info()
        self.assertEqual(
            sorted(locked["company_locked_ids"]), sorted(self.group.company_ids.ids)
        )

    # --- Selección de grupo equivale a tildar las empresas ------------------
    def test_free_user_group_selection_matches_manual(self):
        ids = self.group.company_ids.ids
        env = self._env(self.free_user, ids)
        self.assertEqual(env.companies.ids, ids)
        self.assertEqual(env.company.id, ids[0])

    # --- Forzado server-side ------------------------------------------------
    def test_locked_user_ignores_foreign_context(self):
        locked_ids = set(self.group.company_ids.ids)
        # intenta operar con una empresa fuera del grupo (que sí tiene permitida)
        env = self._env(self.locked_user, [self.c3.id])
        self.assertEqual(set(env.companies.ids), locked_ids)
        self.assertIn(env.company.id, locked_ids)
        # sin contexto: tampoco se expande a todas sus empresas
        env = self._env(self.locked_user)
        self.assertEqual(set(env.companies.ids), locked_ids)

    def test_locked_user_ignores_unauthorized_context(self):
        """Ni siquiera falla con una empresa ajena: se ignora el valor."""
        other = self.env["res.company"].create({"name": "CGS ajena"})
        env = self._env(self.locked_user, [other.id])
        self.assertEqual(set(env.companies.ids), set(self.group.company_ids.ids))

    # --- Endurecimiento: contexto crudo (código que no usa env.companies) ----
    def test_raw_context_key_is_clamped_for_locked_user(self):
        """Wizards que leen env.context['allowed_company_ids'] ven solo el alcance."""
        locked_ids = list(self.locked_user._get_locked_company_ids())
        env = self._env(self.locked_user, [self.c3.id])
        self.assertEqual(env.context["allowed_company_ids"], locked_ids)
        # patrón usado por los wizards de l10n_ar_eynes
        seen = self.env["res.company"].browse(
            env.context.get("allowed_company_ids", [])
        )
        self.assertEqual(set(seen.ids), set(self.group.company_ids.ids))
        self.assertNotIn(self.c3, seen)

    def test_raw_context_key_dropped_ids_outside_scope(self):
        inside = self.group.company_ids[0]
        env = self._env(self.locked_user, [inside.id, self.c3.id])
        self.assertEqual(env.context["allowed_company_ids"], [inside.id])

    def test_raw_context_key_injected_when_missing(self):
        env = self._env(self.locked_user)
        self.assertEqual(
            env.context["allowed_company_ids"],
            list(self.locked_user._get_locked_company_ids()),
        )

    def test_with_company_inside_scope_is_respected(self):
        """with_company(B) dentro del grupo sigue funcionando (no se pisa)."""
        locked_ids = list(self.locked_user._get_locked_company_ids())
        other = self.env["res.company"].browse(locked_ids[-1])
        env = self._env(self.locked_user)
        env = env(context=dict(env.context, allowed_company_ids=[other.id]))
        self.assertEqual(env.company, other)
        self.assertEqual(env.companies, other)

    def test_with_company_outside_scope_is_clamped_unless_sudo_first(self):
        outside = self.c3.id
        locked_ids = list(self.locked_user._get_locked_company_ids())
        env = self._env(self.locked_user)
        # no-sudo: se recorta al alcance
        clamped = env(context=dict(env.context, allowed_company_ids=[outside]))
        self.assertEqual(clamped.context["allowed_company_ids"], locked_ids)
        # sudo primero y recién después la empresa externa: se respeta
        sudo = env(su=True)
        sudo = sudo(context=dict(sudo.context, allowed_company_ids=[outside]))
        self.assertEqual(sudo.companies, self.c3)

    def test_raw_context_untouched_for_free_user(self):
        env = self._env(self.free_user, [self.c3.id])
        self.assertEqual(env.context["allowed_company_ids"], [self.c3.id])

    def test_free_user_still_validated_by_core(self):
        other = self.env["res.company"].create({"name": "CGS ajena 2"})
        env = self._env(self.partial_user, [other.id])
        with self.assertRaises(AccessError):
            env.companies  # noqa: B018

    def test_locked_user_without_group_uses_default_company(self):
        self.locked_user.write({"assigned_company_group_id": False})
        env = self._env(self.locked_user, [self.c2.id, self.c3.id])
        self.assertEqual(env.companies, self.c1)
        self.assertEqual(env.company, self.c1)

    def test_locked_user_record_rules_follow_forced_companies(self):
        """Las record rules multi-empresa usan env.companies: solo ve sus empresas."""
        Partner = self.env["res.partner"].sudo()
        p3 = Partner.create({"name": "CGS P3", "company_id": self.c3.id})
        p1 = Partner.create({"name": "CGS P1", "company_id": self.c1.id})
        env = self._env(self.locked_user, [self.c3.id])
        visible = env["res.partner"].search([("id", "in", (p1 | p3).ids)])
        self.assertIn(p1, visible)
        self.assertNotIn(p3, visible)

    def test_sudo_env_not_affected(self):
        """Operaciones inter-company en sudo mantienen el comportamiento nativo."""
        env = self.env(
            user=self.locked_user,
            context={"allowed_company_ids": [self.c3.id]},
            su=True,
        )
        self.assertEqual(env.companies, self.c3)

    def test_permission_toggle_clears_cache(self):
        self.assertTrue(self.locked_user._get_locked_company_ids())
        self.locked_user.can_switch_company = True
        self.assertIsNone(self.locked_user._get_locked_company_ids())
        self.locked_user.can_switch_company = False
        self.assertTrue(self.locked_user._get_locked_company_ids())

    # --- Consistencia -------------------------------------------------------
    def test_locked_user_requires_group_access(self):
        with self.assertRaises(ValidationError):
            self.locked_user.company_ids = [(3, self.c2.id)]

    def test_group_edit_cannot_break_locked_user(self):
        other = self.env["res.company"].create({"name": "CGS ajena 3"})
        with self.assertRaises(ValidationError):
            self.group.company_ids = [(4, other.id)]

    def test_group_requires_companies(self):
        with self.assertRaises(ValidationError):
            self.env["res.company.group"].create(
                {"name": "vacío", "company_ids": [(6, 0, [])]}
            )

    # --- Seguridad del modelo ----------------------------------------------
    def test_normal_user_cannot_edit_groups(self):
        with self.assertRaises(AccessError):
            self.group.with_user(self.free_user).write({"name": "hack"})

    def test_normal_user_sees_only_groups_of_own_companies(self):
        stranger = self.env["res.company"].create({"name": "CGS lejana"})
        hidden = self.env["res.company.group"].create(
            {"name": "CGS oculto", "company_ids": [(6, 0, [stranger.id])]}
        )
        visible = self.env["res.company.group"].with_user(self.free_user).search([])
        self.assertIn(self.group, visible)
        self.assertNotIn(hidden, visible)
        admin_visible = (
            self.env["res.company.group"]
            .with_user(self.env.ref("base.user_admin"))
            .search([])
        )
        self.assertIn(hidden, admin_visible)

    def test_locked_user_computes_color_of_company_outside_scope(self):
        """El color de empresas fuera del alcance se calcula sin AccessError.

        El formulario del usuario pide company_ids con color; si el partner
        de una empresa del usuario fuera del grupo tiene company_id propio, la
        regla de res.partner lo niega con el contexto recortado y el cliente
        recarga en bucle.
        """
        self.c3.partner_id.sudo().company_id = self.c3
        env = self._env(self.locked_user, [self.c3.id])
        self.assertNotIn(self.c3.id, env.companies.ids)
        self.env.invalidate_all()
        company = self.c3.with_env(env)
        with env.protecting([company._fields["color"]], company):
            company._compute_color()
        self.assertEqual(company.color, self.c3.partner_id.color or self.c3.id % 12)
