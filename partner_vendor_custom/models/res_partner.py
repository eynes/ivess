# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cbu = fields.Char(string='CBU')
    cvu = fields.Char(string='CVU')
    is_admin = fields.Boolean(compute='_compute_is_admin')

    @api.depends_context('uid')
    def _compute_is_admin(self):
        for record in self:
            # Verifica si el usuario actual tiene el grupo de Administrador
            record.is_admin = self.env.user.has_group('base.group_system')

    @api.constrains('email', 'supplier_rank')
    def _check_vendor_email(self):
        for partner in self:
            if partner.supplier_rank > 0 and not partner.email:
                raise ValidationError(_("El email es obligatorio para proveedores."))

    @api.constrains('cbu')
    def _check_cbu_format(self):
        for partner in self:
            if partner.cbu and not re.fullmatch(r'\d{22}', partner.cbu):
                raise ValidationError(_("El CBU debe contener exactamente 22 dígitos numéricos."))
