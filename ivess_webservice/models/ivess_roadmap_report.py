from odoo import api, fields, models, tools


def _format_float_time(value):
    if not value and value != 0:
        return False
    hours = int(value)
    minutes = round((value - hours) * 60)
    return "%02d:%02d" % (hours, minutes)


class IvessRoadmapReport(models.Model):
    _name = "ivess.roadmap.report"
    _description = "Vista SQL de roadmap expuesta al middleware Ivess"
    _auto = False

    customer_code = fields.Char(readonly=True)
    day = fields.Selection(
        [
            ("monday", "Lunes"),
            ("tuesday", "Martes"),
            ("wednesday", "Miércoles"),
            ("thursday", "Jueves"),
            ("friday", "Viernes"),
            ("saturday", "Sábado"),
            ("sunday", "Domingo"),
        ],
        readonly=True,
    )
    receipt_required = fields.Boolean(readonly=True)
    name = fields.Char(readonly=True)
    avg_hour = fields.Float(readonly=True)
    partner_latitude = fields.Float(readonly=True)
    partner_longitude = fields.Float(readonly=True)
    street = fields.Char(readonly=True)
    street2 = fields.Char(readonly=True)
    street_number = fields.Char(readonly=True)
    floor = fields.Char(readonly=True)
    door = fields.Char(readonly=True)
    apartment = fields.Char(readonly=True)
    partner_type_id = fields.Many2one("client.type", readonly=True)
    city = fields.Char(readonly=True)
    phone = fields.Char(readonly=True)
    delivery_number_id = fields.Many2one("delivery.route.number", readonly=True)
    property_payment_term_id = fields.Many2one("account.payment.term", readonly=True)
    property_account_position_id = fields.Many2one("account.fiscal.position", readonly=True)
    vat = fields.Char(readonly=True)
    final_balance = fields.Float(readonly=True)
    state = fields.Selection(
        [
            ("discharge_review", "Revisión de baja"),
            ("holidays", "Vacaciones"),
            ("inactive", "Inactivo"),
        ],
        readonly=True,
    )
    date_to = fields.Date(readonly=True)
    date_from = fields.Date(readonly=True)
    frio_calor_count = fields.Integer(readonly=True)
    lts_min_bonification = fields.Integer(readonly=True)
    consumption_liters = fields.Float(readonly=True)
    overdue_balance = fields.Float(readonly=True)
    mobile_number = fields.Char(readonly=True)
    address_details = fields.Text(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW {table} AS (
                SELECT
                    drl.id                              AS id,
                    drl.customer_code                   AS customer_code,
                    tdr.day                             AS day,
                    rp.x_studio_requiere_comprobante    AS receipt_required,
                    rp.name                             AS name,
                    rp.average_hour                     AS avg_hour,
                    rp.partner_latitude                 AS partner_latitude,
                    rp.partner_longitude                AS partner_longitude,
                    rp.street                           AS street,
                    rp.street2                          AS street2,
                    rp.num                              AS street_number,
                    rp.floor                            AS floor,
                    rp.door                             AS door,
                    rp.apartment                        AS apartment,
                    rp.partner_type_id                  AS partner_type_id,
                    rp.city                             AS city,
                    rp.phone                            AS phone,
                    rp.mobile_number                    AS mobile_number,
                    tdr.delivery_number_id              AS delivery_number_id,
                    rp.address_details                  AS address_details,
                    rp.vat                              AS vat,
                    rp.final_balance                    AS final_balance,
                    rp.state                            AS state,
                    rp.date_to                          AS date_to,
                    rp.date_from                        AS date_from,
                    (
                        SELECT COUNT(*)
                        FROM water_container wc
                        WHERE wc.partner_id = rp.id
                        AND wc.is_frio_calor = TRUE
                    )                                   AS frio_calor_count,
                    (
                        SELECT pt.litros_min_bonificacion
                        FROM product_template pt
                        WHERE pt.is_frio_calor = TRUE
                    )                                   AS lts_min_bonification,
                    (
                        SELECT rpwc.consumption_liters
                        FROM res_partner_water_consumption rpwc
                        WHERE rpwc.partner_id = rp.id
                        AND rpwc.month = EXTRACT(MONTH FROM CURRENT_DATE)
                        AND rpwc.year  = EXTRACT(YEAR  FROM CURRENT_DATE)
                    )                                   AS consumption_liters,
                    (
                        SELECT COALESCE(SUM(am.amount_total_in_currency_signed), 0)
                        FROM account_move am
                        WHERE am.partner_id = rp.id
                        AND am.move_type IN ('out_invoice', 'out_refund')
                        AND am.state = 'posted'
                        AND am.amount_residual != 0
                        AND am.invoice_date_due <= CURRENT_DATE - INTERVAL '90 days'
                    )                                   AS overdue_balance
                FROM delivery_route_line drl
                JOIN template_delivery_route tdr ON drl.template_route_id = tdr.id
                JOIN res_partner rp ON drl.client_id = rp.id
            )
            """.format(table=self._table)
        )

    @api.model
    def get_roadmap(self, **kwargs):
        allowed_params = {"customer_code", "distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: customer_code, distribution."
                        % ", ".join(sorted(unknown_params))
            }

        customer_code = kwargs.get("customer_code")
        distribution = kwargs.get("distribution")

        if not customer_code and not distribution:
            return {
                "error": "Se requiere al menos uno de los siguientes parámetros: customer_code, distribution."
            }
        if customer_code and distribution:
            return {
                "error": "Los parámetros customer_code y distribution son mutuamente excluyentes. "
                        "Envíe solo uno de ellos."
            }

        for param_name, param_value in [("customer_code", customer_code), ("distribution", distribution)]:
            if param_value is not None and not isinstance(param_value, str):
                return {
                    "error": "El parámetro '%s' debe ser una cadena de texto. "
                            "Tipo recibido: %s." % (param_name, type(param_value).__name__)
                }

        if customer_code:
            if not self.env["res.partner"].search([("customer_code", "=", customer_code)], limit=1):
                return {"error": "No existe ningún cliente con el código '%s'." % customer_code}
            domain = [("customer_code", "=", customer_code)]
        else:
            template_routes = self.env["template.delivery.route"].search([("name", "=", distribution)])
            if not template_routes:
                return {"error": "No existe ninguna distribución con el código '%s'." % distribution}
            route_line_ids = self.env["delivery.route.line"].search([
                ("template_route_id", "in", template_routes.ids)
            ]).ids
            domain = [("id", "in", route_line_ids)] if route_line_ids else [("id", "=", False)]

        records = self.search(domain, order="customer_code").read([
            "customer_code",
            "day",
            "receipt_required",
            "name",
            "avg_hour",
            "partner_latitude",
            "partner_longitude",
            "street",
            "street2",
            "street_number",
            "floor",
            "door",
            "apartment",
            "partner_type_id",
            "city",
            "phone",
            "mobile_number",
            "delivery_number_id",
            "address_details",
            "vat",
            "final_balance",
            "state",
            "date_to",
            "date_from",
            "frio_calor_count",
            "lts_min_bonification",
            "consumption_liters",
            "overdue_balance",
        ])

        grouped = {}
        for rec in records:
            code = rec["customer_code"]
            if code not in grouped:
                grouped[code] = {
                    "customer_code": code,
                    "day": rec["day"],
                    "receipt_required": rec["receipt_required"],
                    "name": rec["name"],
                    "avg_hour": _format_float_time(rec["avg_hour"]),
                    "partner_latitude": rec["partner_latitude"],
                    "partner_longitude": rec["partner_longitude"],
                    "street": rec["street"],
                    "street2": rec["street2"],
                    "street_number": rec["street_number"],
                    "floor": rec["floor"],
                    "door": rec["door"],
                    "apartment": rec["apartment"],
                    "partner_type_id": rec["partner_type_id"],
                    "city": rec["city"],
                    "frio_calor_count": rec["frio_calor_count"],
                    "lts_min_bonification": rec["lts_min_bonification"],
                    "consumption_liters": rec["consumption_liters"],
                    "phone": rec["phone"],
                    "mobile_number": rec["mobile_number"],
                    "delivery_number_id": rec["delivery_number_id"],
                    "address_details": rec["address_details"],
                    "property_payment_term_id": False,
                    "vat": rec["vat"],
                    "final_balance": rec["final_balance"],
                    "overdue_balance": rec["overdue_balance"],
                    "property_account_position_id": False,
                    "state": rec["state"],
                    "date_from": rec["date_from"],
                    "date_to": rec["date_to"],
                }
            
        partners = self.env["res.partner"].search([("customer_code", "in", list(grouped.keys()))])
        for partner in partners:
            code = partner.customer_code
            if code not in grouped:
                continue
            pterm = partner.property_payment_term_id
            fpos = partner.property_account_position_id
            grouped[code]["property_payment_term_id"] = (pterm.id, pterm.display_name) if pterm else False
            grouped[code]["property_account_position_id"] = (fpos.id, fpos.display_name) if fpos else False

        return list(grouped.values())
