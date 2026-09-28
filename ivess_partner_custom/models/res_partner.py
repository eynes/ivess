from collections import defaultdict

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    requiere_comprobante = fields.Boolean(
        string="Requiere Factura",
    )
    codigo_bejerman = fields.Char(
        string="Código Bejerman",
        copy=False,
    )
    fecha_alta = fields.Datetime(
        string="Fecha de Alta",
        help="Fecha de alta del cliente en el sistema origen (no confundir"
        " con create_date, que es cuándo se creó el registro en Odoo).",
        copy=False,
    )
    regimen_facturacion = fields.Selection(
        selection=[
            ("contraentrega", "Contraentrega"),
            ("mensual", "Mensual"),
        ],
        string="Régimen de Facturación",
        help="Define si al cliente se le emite remito o factura y con qué"
        " frecuencia.",
        tracking=True,
    )
    pagador_modo = fields.Selection(
        selection=[
            ("madre", "Madre"),
            ("especifico", "Contacto específico"),
            ("autopago", "Autopago"),
        ],
        string="Tipo de Pagador",
        default="madre",
        required=True,
        tracking=True,
        help="Madre: paga la cuenta madre, o la propia cuenta si no tiene"
        " madre. Contacto específico: paga el contacto que se elija a mano."
        " Autopago: paga la propia cuenta.",
    )
    pagador_id = fields.Many2one(
        comodel_name="res.partner",
        string="Pagador",
        compute="_compute_pagador_id",
        store=True,
        readonly=False,
        copy=False,
        index=True,
        help="Contacto que se hace cargo de la deuda de esta cuenta.",
    )
    delivery_street = fields.Char(string="Calle de Entrega")
    delivery_street2 = fields.Char(string="Calle 2 de Entrega")
    delivery_street_name = fields.Char(
        string="Nombre de Calle de Entrega",
        compute="_compute_delivery_street_data",
        inverse="_inverse_delivery_street_data",
        store=True,
    )
    delivery_street_number = fields.Char(
        string="Altura de Entrega",
        compute="_compute_delivery_street_data",
        inverse="_inverse_delivery_street_data",
        store=True,
    )
    delivery_street_number2 = fields.Char(
        string="Altura 2 de Entrega",
        compute="_compute_delivery_street_data",
        inverse="_inverse_delivery_street_data",
        store=True,
    )
    delivery_num = fields.Char(string="Número de Entrega", size=5)
    delivery_floor = fields.Char(string="Piso de Entrega", size=3)
    delivery_door = fields.Char(string="Puerta de Entrega", size=3)
    delivery_apartment = fields.Char(string="Departamento de Entrega", size=4)
    delivery_city = fields.Char(string="Ciudad de Entrega")
    delivery_city_id = fields.Many2one(
        comodel_name="res.city",
        string="Ciudad de Entrega (ID)",
    )
    delivery_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Provincia de Entrega",
        domain="[('country_id', '=?', delivery_country_id)]",
    )
    delivery_zip = fields.Char(string="Código Postal de Entrega")
    delivery_country_id = fields.Many2one(
        comodel_name="res.country",
        string="País de Entrega",
    )
    delivery_country_enforce_cities = fields.Boolean(
        related="delivery_country_id.enforce_cities",
    )
    # state_id = fields.Many2one(
    #     required=True,
    # )
    # property_supplier_payment_term_id = fields.Many2one(
    #     required=True,
    # )
    unbilled_balance = fields.Monetary(
        string="Unbilled Balance",
        compute="_compute_balances",
        store=True,
    )
    final_balance = fields.Monetary(
        string="Final Balance",
        compute="_compute_balances",
        store=True,
    )

    @api.depends(
        "sale_order_ids",
        "sale_order_ids.invoice_status",
        "sale_order_ids.invoice_ids",
        "sale_order_ids.invoice_ids.state",
        "sale_order_ids.invoice_ids.payment_state",
        "sale_order_ids.amount_total",
        "sale_order_ids.state",
    )
    def _compute_balances(self):
        payments_data = self.env["account.payment.order"].search_read(
            domain=[
                ("partner_id", "in", self.ids),
                ("state", "=", "posted"),
                ("type", "=", "receipt"),
            ],
            fields=["partner_id", "amount"],
        )
        payment_totals = defaultdict(float)
        for payment in payments_data:
            payment_totals[payment["partner_id"][0]] += payment["amount"]

        for partner in self:
            unbilled = 0.0
            total_orders = 0.0
            confirmed_orders = partner.sale_order_ids.filtered(
                lambda s: s.state in ["sale", "done"]
            )
            for order in confirmed_orders:
                total_orders += order.amount_total
                if order.invoice_status == "to invoice":
                    unbilled += order.amount_total

            partner.unbilled_balance = unbilled
            partner.final_balance = total_orders - payment_totals.get(partner.id, 0.0)

    @api.depends("pagador_modo", "parent_id")
    def _compute_pagador_id(self):
        for partner in self:
            if partner.pagador_modo == "especifico":
                partner.pagador_id = partner.pagador_id
            elif partner.pagador_modo == "madre" and partner.parent_id:
                partner.pagador_id = partner.parent_id
            else:
                # _origin: un contacto nuevo todavía no tiene id propio al
                # que apuntar; se completa al guardarlo.
                partner.pagador_id = partner._origin

    # La dirección de entrega replica a la actual: mismo corte de calle que
    # base_address_extended hace sobre street y mismos onchanges de país,
    # provincia y ciudad.
    @api.depends("delivery_street")
    def _compute_delivery_street_data(self):
        for partner in self:
            split = tools.street_split(partner.delivery_street)
            partner.delivery_street_name = split["street_name"]
            partner.delivery_street_number = split["street_number"]
            partner.delivery_street_number2 = split["street_number2"]

    def _inverse_delivery_street_data(self):
        for partner in self:
            street = (
                (partner.delivery_street_name or "")
                + " "
                + (partner.delivery_street_number or "")
            ).strip()
            if partner.delivery_street_number2:
                street = street + " - " + partner.delivery_street_number2
            partner.delivery_street = street

    @api.onchange("delivery_country_id")
    def _onchange_delivery_country_id(self):
        country = self.delivery_country_id
        if country and country != self.delivery_state_id.country_id:
            self.delivery_state_id = False
        if country and country != self.delivery_city_id.country_id:
            self.delivery_city_id = False

    @api.onchange("delivery_state_id")
    def _onchange_delivery_state_id(self):
        state_country = self.delivery_state_id.country_id
        if state_country and self.delivery_country_id != state_country:
            self.delivery_country_id = state_country

    @api.onchange("delivery_city_id")
    def _onchange_delivery_city_id(self):
        if self.delivery_city_id:
            self.delivery_city = self.delivery_city_id.name
            self.delivery_zip = self.delivery_city_id.zipcode
            self.delivery_state_id = self.delivery_city_id.state_id
        elif self._origin:
            self.delivery_city = False
            self.delivery_zip = False
            self.delivery_state_id = False

    @api.constrains("codigo_bejerman")
    def _check_codigo_bejerman(self):
        for partner in self:
            if not partner.codigo_bejerman:
                continue
            duplicate = self.with_context(active_test=False).search(
                [
                    ("codigo_bejerman", "=", partner.codigo_bejerman),
                    ("company_id", "=", partner.company_id.id),
                    ("id", "!=", partner.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Ya existe un contacto con el Código Bejerman '%s'.")
                    % partner.codigo_bejerman
                )

    @api.constrains("regimen_facturacion", "parent_id")
    def _check_regimen_facturacion_grupo(self):
        etiquetas = dict(self._fields["regimen_facturacion"].selection)
        # sudo: el resultado no puede depender de qué compañías ve el usuario.
        for partner in self.sudo():
            madres = partner.parent_id | partner.filtered("child_ids")
            for madre in madres:
                grupo = (madre | madre.child_ids).filtered("regimen_facturacion")
                if len(set(grupo.mapped("regimen_facturacion"))) > 1:
                    detalle = "\n".join(
                        "- %s: %s"
                        % (
                            cuenta.name or cuenta.display_name,
                            etiquetas[cuenta.regimen_facturacion],
                        )
                        for cuenta in grupo
                    )
                    raise ValidationError(
                        _(
                            "Todas las cuentas del grupo de «%(madre)s» tienen que tener"
                            " el mismo régimen de facturación. Así quedarían:\n%(detalle)s"
                        )
                        % {"madre": madre.display_name, "detalle": detalle}
                    )

    def write(self, vals):
        self._check_pending_water_containers_before_archiving(vals)
        return super().write(vals)

    def _set_multicompany_account_fiscal_position(self, property_account_position_id):
        # l10n_ar_eynes propaga property_account_position_id a las otras
        # compañías escribiendo el campo, lo que dispara write() de nuevo
        # y por ende otra llamada a este método: sin este guard entra en
        # recursión infinita (ping-pong entre compañías) y termina en
        # RecursionError / RPC_ERROR.
        if self.env.context.get("skip_multicompany_fiscal_position"):
            return
        return super(
            ResPartner,
            self.with_context(skip_multicompany_fiscal_position=True),
        )._set_multicompany_account_fiscal_position(property_account_position_id)

    def unlink(self):
        for partner in self:
            partner._check_pending_water_containers_before_archiving()
        return super().unlink()

    def _check_pending_water_containers_before_archiving(self, vals=None):
        """Valida si hay envases pendientes al intentar archivar o eliminar."""
        if self.env.user.has_group(
            "logistic_custom_ivess.group_allow_archive_debt_or_containers"
        ):
            return

        if vals is None or vals.get("active") is False:
            errors = []
            for partner in self:
                pending = partner.check_water_container()
                unpaid = partner.get_unpaid_invoice_count()
                if pending > 0:
                    errors.append(
                        _("This customer has %s water containers pending return.")
                        % pending
                    )
                if unpaid > 0:
                    errors.append(
                        _("This customer has %s unpaid or partially paid invoice(s).")
                        % unpaid
                    )
            if errors:
                raise UserError("\n".join(errors))

    def check_water_container(self):
        self.ensure_one()
        containers = self.env["water.container"].search(
            [
                ("partner_id", "=", self.id),
            ]
        )
        return sum(containers.mapped("quantity"))

    def get_unpaid_invoice_count(self):
        self.ensure_one()
        return self.env["account.move"].search_count(
            [
                ("partner_id", "=", self.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
            ]
        )
