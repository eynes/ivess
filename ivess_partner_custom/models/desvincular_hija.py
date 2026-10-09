from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IvessDesvincularHija(models.TransientModel):
    _name = "ivess.desvincular.hija"
    _description = "Desvincular una cuenta hija de su grupo"

    hija_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cuenta hija",
        required=True,
        readonly=True,
    )
    madre_id = fields.Many2one(
        related="hija_id.parent_id",
        string="Grupo del que sale",
    )
    regimen_facturacion = fields.Selection(
        selection=lambda self: self.env["res.partner"]._fields["regimen_facturacion"].selection,
        string="Régimen de Facturación",
        compute="_compute_valores_actuales",
        readonly=False,
        store=True,
    )
    pagador_modo = fields.Selection(
        selection=lambda self: self.env["res.partner"]._fields["pagador_modo"].selection,
        string="Tipo de Pagador",
        compute="_compute_valores_actuales",
        readonly=False,
        store=True,
        required=True,
    )
    pagador_id = fields.Many2one(
        comodel_name="res.partner",
        string="Pagador",
        compute="_compute_valores_actuales",
        readonly=False,
        store=True,
    )
    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Lista de Precios",
        compute="_compute_valores_actuales",
        readonly=False,
        store=True,
        required=True,
    )

    @api.depends("hija_id")
    def _compute_valores_actuales(self):
        for wizard in self:
            hija = wizard.hija_id
            wizard.regimen_facturacion = hija.regimen_facturacion
            wizard.pagador_modo = hija.pagador_modo or "madre"
            wizard.pagador_id = hija.pagador_id if hija.pagador_modo == "especifico" else False
            wizard.pricelist_id = hija.property_product_pricelist

    def action_confirmar(self):
        self.ensure_one()
        hija, madre = self.hija_id, self.madre_id
        if not madre:
            raise UserError(_("%s no pertenece a ningún grupo.") % hija.display_name)
        if self.pagador_modo == "especifico" and not self.pagador_id:
            raise UserError(_("Elegí quién paga la cuenta."))
        vals = {
            "parent_id": False,
            "type": "contact",
            "regimen_facturacion": self.regimen_facturacion,
            "pagador_modo": self.pagador_modo,
            "property_product_pricelist": self.pricelist_id.id,
        }
        if self.pagador_modo == "especifico":
            vals["pagador_id"] = self.pagador_id.id
        if "csv_inherit_commercial" in hija._fields:
            vals["csv_inherit_commercial"] = False
        hija.write(vals)
        hija.message_post(body=_("Se desvinculó del grupo de %s y quedó como cuenta individual.") % madre.display_name)
        madre.message_post(body=_("%s se desvinculó del grupo.") % hija.display_name)
        return {"type": "ir.actions.act_window_close"}
