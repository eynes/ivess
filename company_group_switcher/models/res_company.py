# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.depends("root_id")
    def _compute_color(self):
        """Lee el color del partner de la empresa raíz con sudo.

        Los usuarios con el cambio de empresa bloqueado operan con el contexto
        recortado a su grupo, pero su formulario muestra todas sus empresas
        (``company_ids`` con color). Si el partner de una empresa fuera del
        alcance tiene ``company_id`` propio, la regla multiempresa de
        ``res.partner`` lo niega y el cliente recarga la página en bucle al
        recibir el AccessError con ``suggested_company``. Es solo el color: no
        se amplía el alcance de empresas.
        """
        for company in self:
            root = company.root_id.sudo()
            company.color = root.partner_id.color or (root._origin.id % 12)
