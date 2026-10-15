# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Forzado server-side del alcance de empresas para usuarios bloqueados.

El core toma ``allowed_company_ids`` del contexto que envía el cliente (cookie
``cids``) y solo valida que sea un subconjunto de las empresas del usuario. Para
un usuario sin permiso de cambio (``can_switch_company = False``) se sanea ese
valor en cada entorno no-sudo:

* se descartan las empresas que están fuera de su empresa/grupo asignado;
* si no queda ninguna (o la clave falta) se usa el alcance completo.

Como se reescribe la clave del contexto, también quedan cubiertos los wizards que
la leen directo de ``env.context`` sin pasar por ``env.companies``. Las empresas
dentro del alcance se respetan (``with_company`` dentro del grupo sigue
funcionando). El modo sudo no se toca (operaciones inter-company); código que
necesite una empresa fuera del alcance debe usar ``sudo()`` antes de cambiarla.
"""

from odoo import SUPERUSER_ID
from odoo.orm.environments import Environment
from odoo.orm.registry import Registry

_PATCH_FLAG = "_company_group_switcher_patched"


def _locked_ids_for(cr, uid):
    """Ids del alcance forzado para ``uid`` en la base de ``cr``, o None."""
    registry = Registry(cr.dbname)
    if not registry.ready or "res.users" not in registry:
        return None
    if not hasattr(registry["res.users"], "_get_locked_company_ids"):
        # el módulo no está instalado en esta base
        return None
    root = Environment(cr, SUPERUSER_ID, {})
    return root["res.users"].browse(uid)._get_locked_company_ids()


def _clamp(requested, locked):
    """Empresas pedidas que están dentro del alcance; todo el alcance si ninguna."""
    if isinstance(requested, (list, tuple)):
        kept = [cid for cid in requested if cid in locked]
        if kept:
            return kept
    return list(locked)


def _patch_env_new():
    original = Environment.__new__
    if getattr(original, _PATCH_FLAG, False):
        return

    def __new__(cls, cr, uid, context, su=False):
        if uid and uid != SUPERUSER_ID and not su:
            locked = _locked_ids_for(cr, uid)
            if locked is not None:
                requested = context.get("allowed_company_ids")
                ids = _clamp(requested, locked)
                if requested != ids:
                    context = dict(context, allowed_company_ids=ids)
        return original(cls, cr, uid, context, su)

    setattr(__new__, _PATCH_FLAG, True)
    Environment.__new__ = __new__


def post_load():
    _patch_env_new()
