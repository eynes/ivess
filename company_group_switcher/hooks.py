# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Forzado server-side de las empresas activas para usuarios bloqueados.

``Environment.companies`` / ``Environment.company`` toman ``allowed_company_ids``
del contexto que envía el cliente (cookie ``cids``) y solo validan que sea un
subconjunto de las empresas del usuario. Para un usuario sin permiso de cambio
(``can_switch_company = False``) se ignora ese valor y se devuelve siempre su
empresa/grupo asignado. No se toca el modo sudo (operaciones inter-company).
"""

import functools

from odoo.orm.environments import Environment

_PATCH_FLAG = "_company_group_switcher_patched"


def _locked_company_ids(env):
    """Tupla de ids forzados para el usuario del entorno, o None si no aplica."""
    if env.su or not env.uid or not env.registry.ready:
        return None
    user = env.user
    if not hasattr(user, "_get_locked_company_ids"):
        # el módulo no está instalado en esta base
        return None
    return user._get_locked_company_ids()


def _wrap(name, build):
    original = Environment.__dict__[name]
    if getattr(original.func, _PATCH_FLAG, False):
        return
    orig_func = original.func

    @functools.wraps(orig_func)
    def wrapper(self):
        locked = _locked_company_ids(self)
        if locked is None:
            return orig_func(self)
        return build(self, locked)

    setattr(wrapper, _PATCH_FLAG, True)
    new = functools.cached_property(wrapper)
    new.__set_name__(Environment, name)
    setattr(Environment, name, new)


def post_load():
    _wrap("companies", lambda env, ids: env["res.company"].browse(ids))
    _wrap("company", lambda env, ids: env["res.company"].browse(ids[0]))
