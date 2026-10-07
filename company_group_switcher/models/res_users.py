# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import SUPERUSER_ID, _, api, fields, models, tools
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    can_switch_company = fields.Boolean(
        string="Puede cambiar de empresa/grupo",
        default=True,
        help="Si se desmarca, el usuario opera siempre con su grupo de empresas "
        "asignado (o con su empresa por defecto si no tiene grupo), sin importar "
        "lo que envíe el navegador.",
    )
    assigned_company_group_id = fields.Many2one(
        "res.company.group",
        string="Grupo de empresas asignado",
        ondelete="restrict",
        help="Grupo con el que opera el usuario cuando no puede cambiar de empresa.",
    )

    @api.model
    def _get_invalidation_fields(self):
        return super()._get_invalidation_fields() | {
            "can_switch_company",
            "assigned_company_group_id",
        }

    @api.constrains(
        "can_switch_company", "assigned_company_group_id", "company_id", "company_ids"
    )
    def _check_assigned_group_access(self):
        for user in self.sudo():
            group = user.assigned_company_group_id
            if user.can_switch_company or not group:
                continue
            missing = group.company_ids - user.company_ids
            if missing:
                raise ValidationError(
                    _(
                        "El usuario '%(user)s' no tiene acceso a todas las empresas "
                        "de su grupo asignado '%(group)s'. Faltan: %(companies)s.",
                        user=user.name,
                        group=group.name,
                        companies=", ".join(missing.mapped("name")),
                    )
                )
            if user.company_id not in group.company_ids:
                raise ValidationError(
                    _(
                        "La empresa por defecto de '%(user)s' debe pertenecer a "
                        "su grupo asignado '%(group)s'.",
                        user=user.name,
                        group=group.name,
                    )
                )

    @tools.ormcache("self.id")
    def _get_locked_company_ids(self):
        """Ids de empresas forzados, o None si el usuario puede cambiar libremente."""
        user = self.sudo()
        if user.id == SUPERUSER_ID or user.can_switch_company:
            return None
        user_company_ids = user._get_company_ids()
        group = user.assigned_company_group_id
        ids = []
        if group and group.active:
            ids = [cid for cid in group.company_ids.ids if cid in user_company_ids]
        default_id = user.company_id.id
        if not ids:
            ids = [default_id]
        elif default_id in ids:
            ids.remove(default_id)
            ids.insert(0, default_id)
        return tuple(ids)

    def _get_company_switcher_info(self):
        """Datos para el web client: grupos ofrecidos y bloqueo."""
        self.ensure_one()
        locked = self._get_locked_company_ids()
        groups = []
        if locked is None:
            for group in self.env["res.company.group"]._get_available_for_user(self):
                groups.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "sequence": group.sequence,
                        "company_ids": group.company_ids.ids,
                    }
                )
        else:
            group = self.sudo().assigned_company_group_id
            if group and group.active:
                groups.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "sequence": group.sequence,
                        "company_ids": list(locked),
                    }
                )
        return {
            "company_groups": groups,
            "company_locked_ids": list(locked) if locked is not None else False,
        }
