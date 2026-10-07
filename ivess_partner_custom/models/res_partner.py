import re
from collections import defaultdict

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

# Campo de la dirección de entrega en la ficha -> campo de dirección del
# contacto de entrega automático.
DELIVERY_ADDRESS_FIELDS = {
    "delivery_street": "street",
    "delivery_street2": "street2",
    "delivery_num": "num",
    "delivery_floor": "floor",
    "delivery_door": "door",
    "delivery_apartment": "apartment",
    "delivery_city": "city",
    "delivery_city_id": "city_id",
    "delivery_state_id": "state_id",
    "delivery_zip": "zip",
    "delivery_country_id": "country_id",
}
# Datos del cliente que el remito imprime del contacto de entrega.
DELIVERY_CONTACT_FIELDS = ("name", "phone", "email")


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
    direccion_completa = fields.Char(
        string="Dirección Completa",
        compute="_compute_direccion_completa",
        store=True,
        index="trigram",
        help="Dirección de facturación, de entrega y observaciones de dirección"
        " en un solo texto, para buscar por cualquier parte.",
    )
    delivery_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto de Entrega Automático",
        copy=False,
        index="btree_not_null",
        ondelete="set null",
        help="Dirección hija de tipo Entrega, archivada, que se mantiene sola"
        " a partir de la dirección de entrega de la ficha. Es la que usan el"
        " pedido, el remito y las percepciones.",
    )
    vat_duplicado_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Contactos con el Mismo CUIT",
        compute="_compute_vat_duplicado_ids",
    )
    alta_madre_id = fields.Many2one(
        comodel_name="res.partner",
        string="Colgar como Hija de",
        compute="_compute_alta_madre_id",
        readonly=False,
    )
    traspaso_destino_id = fields.Many2one(
        comodel_name="res.partner",
        string="Saldo Traspasado a",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
    traspaso_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento de Traspaso",
        readonly=True,
        copy=False,
    )
    traspaso_origen_ids = fields.One2many(
        comodel_name="res.partner",
        inverse_name="traspaso_destino_id",
        string="Recibió Saldo de",
        context={"active_test": False},
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

    @api.depends(
        "street", "num", "floor", "door", "apartment", "street2", "city", "zip",
        "delivery_street", "delivery_num", "delivery_floor", "delivery_door",
        "delivery_apartment", "delivery_street2", "delivery_city", "delivery_zip",
        "address_details",
    )
    def _compute_direccion_completa(self):
        for partner in self:
            facturacion = partner._texto_direccion("")
            entrega = partner._texto_direccion("delivery_")
            partes = [facturacion, entrega and _("Entrega: %s") % entrega, partner.address_details]
            partner.direccion_completa = " | ".join(p for p in partes if p) or False

    def _texto_direccion(self, prefijo):
        """Calle y número juntos (así "Mitre 500" se encuentra aunque estén
        en campos separados), después piso, puerta, depto, ciudad y CP."""
        valor = lambda campo: self[prefijo + campo] or ""
        texto = " ".join(filter(None, [valor("street"), valor("num")]))
        for campo, etiqueta in (("floor", _("piso")), ("door", _("puerta")), ("apartment", _("depto"))):
            if valor(campo):
                texto += " %s %s" % (etiqueta, valor(campo))
        for campo in ("street2", "city"):
            if valor(campo):
                texto += ", " + valor(campo)
        if valor("zip"):
            texto += " (%s)" % valor("zip")
        return texto.strip(", ")

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

    @api.depends("vat", "document_type_id", "parent_id")
    def _compute_vat_duplicado_ids(self):
        """Contactos que ya tienen el CUIT/CUIL que se está cargando en un
        alta. Mismo criterio que check_vat_duplicated de l10n_ar_eynes: mismo
        número y tipo de documento, entre contactos sin madre."""
        tipos = self.env["res.document.type"]
        for xmlid in ("l10n_ar_eynes.document_cuit", "l10n_ar_eynes.document_cuil"):
            tipos |= self.env.ref(xmlid, raise_if_not_found=False) or tipos
        for partner in self:
            vat = re.sub(r"\D", "", partner.vat or "")
            if (
                partner._origin.id
                or partner.parent_id
                or not vat
                or partner.document_type_id not in tipos
            ):
                partner.vat_duplicado_ids = False
                continue
            partner.vat_duplicado_ids = self.search(
                [
                    ("vat", "=", vat),
                    ("document_type_id", "=", partner.document_type_id.id),
                    ("parent_id", "=", False),
                ]
            )

    def _compute_alta_madre_id(self):
        self.alta_madre_id = False

    @api.onchange("alta_madre_id")
    def _onchange_alta_madre_id(self):
        # Se cuelga como las hijas que carga la importación de contactos:
        # tipo "other" para que Odoo no le pise la dirección con la de la madre.
        if self.alta_madre_id:
            self.parent_id = self.alta_madre_id
            self.type = "other"
            if "csv_inherit_commercial" in self._fields:
                self.csv_inherit_commercial = True

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # "type" no está en la ficha para un usuario común, así que lo que
            # puso el onchange de alta_madre_id no llega: se aplica acá.
            madre_id = vals.pop("alta_madre_id", False)
            if madre_id:
                vals.update(parent_id=madre_id, type="other")
                if "csv_inherit_commercial" in self._fields:
                    vals["csv_inherit_commercial"] = True
        partners = super().create(vals_list)
        if not self.env.context.get("sync_delivery_partner"):
            partners.filtered(
                lambda p: p._has_delivery_address()
            )._sync_delivery_partner()
        return partners

    def write(self, vals):
        if vals.get("active") is False:
            self._check_madres_sin_hijas_activas()
        self._check_pending_water_containers_before_archiving(vals)
        res = super().write(vals)
        if not self.env.context.get("sync_delivery_partner"):
            if vals.keys() & (set(DELIVERY_ADDRESS_FIELDS) | set(DELIVERY_CONTACT_FIELDS)):
                self.filtered(
                    lambda p: p.delivery_partner_id or p._has_delivery_address()
                )._sync_delivery_partner()
            if vals.keys() & set(DELIVERY_ADDRESS_FIELDS.values()):
                self._sync_delivery_partner_back()
        return res

    def action_archive(self):
        # Una madre con hijas activas no se archiva directo: se abre la
        # elección de la nueva madre (el cliente web ejecuta la acción).
        if len(self) == 1 and self._hijas_activas():
            return {
                "type": "ir.actions.act_window",
                "name": _("Dar de baja una cuenta madre"),
                "res_model": "ivess.baja.madre",
                "view_mode": "form",
                # action_archive llega por call_kw, no por call_button: nadie
                # completa "views" y el cliente web falla si no viene.
                "views": [(False, "form")],
                "target": "new",
                "context": {"default_madre_id": self.id},
            }
        return super().action_archive()

    def _hijas_activas(self):
        """Cuentas hijas: las que cuelgan de la madre como "other", como las
        carga import_partners (las personas de contacto no cuentan)."""
        self.ensure_one()
        return self.child_ids.filtered(lambda child: child.type == "other")

    def _saldo_a_cobrar(self, company):
        """Saldo a cobrar registrado a nombre de la cuenta. En una madre incluye
        lo facturado a sus hijas, que Odoo registra en la cuenta comercial."""
        self.ensure_one()
        lines = self.env["account.move.line"].search(
            [
                ("partner_id", "=", self.id),
                ("company_id", "=", company.id),
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
            ]
        )
        return sum(lines.mapped("balance"))

    def _check_madres_sin_hijas_activas(self):
        madres = self.filtered(lambda partner: partner._hijas_activas())
        if madres:
            raise UserError(
                _(
                    "No se puede dar de baja una cuenta madre con hijas activas sin elegir"
                    " cuál pasa a ser la nueva madre:\n%s\n\nArchivala desde su ficha, de a"
                    " una, para elegirla."
                )
                % "\n".join(
                    "- %s: %s"
                    % (madre.display_name, ", ".join(madre._hijas_activas().mapped("name")))
                    for madre in madres
                )
            )

    def _reasignar_hijas(self, nueva_madre):
        """La hija elegida queda sin madre y las demás hijas pasan a colgar
        de ella."""
        self.ensure_one()
        hijas = self._hijas_activas()
        if nueva_madre not in hijas:
            raise UserError(_("La nueva madre tiene que ser una de las hijas activas."))
        vals = {"parent_id": False, "type": "contact"}
        if "csv_inherit_commercial" in self._fields:
            vals["csv_inherit_commercial"] = False
        nueva_madre.write(vals)
        (hijas - nueva_madre).write({"parent_id": nueva_madre.id})
        self.message_post(
            body=_("Baja de la cuenta madre: %(nueva)s pasa a ser la nueva madre de %(hijas)s.")
            % {
                "nueva": nueva_madre.display_name,
                "hijas": ", ".join((hijas - nueva_madre).mapped("name")) or _("ninguna otra hija"),
            }
        )

    def address_get(self, adr_pref=None):
        result = super().address_get(adr_pref)
        if len(self) == 1 and self.delivery_partner_id and "delivery" in (adr_pref or ()):
            result["delivery"] = self.delivery_partner_id.id
        return result

    def _has_delivery_address(self):
        self.ensure_one()
        return any(self[field] for field in DELIVERY_ADDRESS_FIELDS)

    def _sync_delivery_partner(self):
        """Crea o actualiza el contacto de entrega automático a partir de la
        dirección de entrega de la ficha. Queda archivado para que no se vea
        como contacto hijo ni lo tomen las hijas al buscar su dirección."""
        for partner in self.with_context(sync_delivery_partner=True):
            if not partner._has_delivery_address():
                if partner.delivery_partner_id:
                    partner.delivery_partner_id = False
                continue
            vals = {
                target: partner._fields[source].convert_to_write(partner[source], partner)
                for source, target in DELIVERY_ADDRESS_FIELDS.items()
            }
            vals.update({field: partner[field] for field in DELIVERY_CONTACT_FIELDS})
            if partner.delivery_partner_id:
                partner.delivery_partner_id.write(vals)
            else:
                vals.update(type="delivery", parent_id=partner.id, active=False)
                partner.delivery_partner_id = partner.create(vals)

    def _sync_delivery_partner_back(self):
        """Si alguien edita la dirección del contacto de entrega automático
        (por ejemplo desde el pedido), la lleva a la ficha del cliente."""
        for shadow in self:
            owner = shadow.parent_id
            if not owner or owner.delivery_partner_id != shadow:
                continue
            owner.with_context(sync_delivery_partner=True).write(
                {
                    source: shadow._fields[target].convert_to_write(shadow[target], shadow)
                    for source, target in DELIVERY_ADDRESS_FIELDS.items()
                }
            )

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
        self._check_clientes_no_se_eliminan()
        for partner in self:
            partner._check_pending_water_containers_before_archiving()
        return super().unlink()

    def _check_clientes_no_se_eliminan(self):
        """Los clientes no se borran: se archivan, para conservar sus vínculos
        y su historial. Solo un administrador puede eliminarlos."""
        if self.env.user.has_group("base.group_system"):
            return
        clientes = self.filtered("is_customer")
        if clientes:
            raise UserError(
                _(
                    "No se pueden eliminar clientes: archivalos para conservar sus vínculos"
                    " y su historial.\n%s"
                )
                % "\n".join("- %s" % cliente.display_name for cliente in clientes[:20])
            )

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
                # Tras un traspaso de saldo las facturas siguen impagas (no se
                # concilian) pero su deuda ya está en la cuenta destino.
                if self.env.context.get("traspaso_saldo_hecho"):
                    unpaid = 0
                else:
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
