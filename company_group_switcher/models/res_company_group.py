# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompanyGroup(models.Model):
    """Grupo de empresas independientes.

    Es solo un objeto de conveniencia de interfaz/contexto: no es una sociedad
    y no interfiere con la contabilidad ni la configuración fiscal.
    """

    _name = "res.company.group"
    _description = "Grupo de empresas"
    _order = "sequence, name"

    name = fields.Char(string="Nombre", required=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    active = fields.Boolean(string="Activo", default=True)
    company_ids = fields.Many2many(
        "res.company",
        "res_company_group_company_rel",
        "group_id",
        "company_id",
        string="Empresas",
        required=True,
    )
    locked_user_ids = fields.One2many(
        "res.users",
        "assigned_company_group_id",
        string="Usuarios con este grupo asignado",
        readonly=True,
    )

    @api.constrains("company_ids")
    def _check_company_ids(self):
        for group in self:
            if not group.company_ids:
                raise ValidationError(
                    _("El grupo '%s' debe tener al menos una empresa.", group.name)
                )

    @api.constrains("company_ids")
    def _check_locked_users_access(self):
        """Los usuarios bloqueados con este grupo deben acceder a todas sus empresas."""
        for group in self.sudo():
            for user in group.locked_user_ids.filtered(
                lambda u: not u.can_switch_company
            ):
                user._check_assigned_group_access()

    @api.model
    def _get_available_for_user(self, user):
        """Grupos activos cuyas empresas están todas habilitadas para el usuario."""
        user_company_ids = set(user._get_company_ids())
        return (
            self.sudo()
            .search([])
            .filtered(
                lambda g: g.company_ids and set(g.company_ids.ids) <= user_company_ids
            )
        )

    def _clear_company_caches(self):
        self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        groups = super().create(vals_list)
        self._clear_company_caches()
        return groups

    def write(self, vals):
        res = super().write(vals)
        self._clear_company_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._clear_company_caches()
        return res
