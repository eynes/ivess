from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    status_in_payment = fields.Selection(
        selection_add=[("x_closed_by_summary", "Cerrado por Resumen")],
    )
    x_folio_legal = fields.Char(
        string="Folio Legal",
        readonly=True,
        copy=False,
        help=(
            "Número de folio correlativo del libro diario legal, asignado "
            "por el proceso de foliación. Se asigna únicamente a los "
            "asientos del Diario de Refundición y de Cierre de Ejercicio, "
            "de forma independiente al número de asiento de gestión."
        ),
    )
    x_is_summary_entry = fields.Boolean(
        string="Es Asiento de Resumen/Neteo",
        readonly=True,
        copy=False,
        help=(
            "Asiento generado por el Asistente de Cierre Mensual (el "
            "neteo en el diario operativo o el resumen en el diario "
            "legal), no un comprobante operativo original."
        ),
    )
    x_closed_by_summary_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Cerrado por Resumen",
        readonly=True,
        copy=False,
        help=(
            "Asiento resumen del Diario Legal que absorbió la línea de "
            "deuda de este comprobante en el cierre mensual. Si a la fecha "
            "de cierre quedaba saldo pendiente, ese saldo viajó a la cuenta "
            "de deuda legal y la cobranza/pago debe gestionarse desde aquí "
            "contra la línea correspondiente de ese asiento resumen. Si el "
            "comprobante ya estaba cobrado/pagado antes del cierre, este "
            "campo solo indica en qué cierre mensual quedó resumido (su "
            "importe fue a la cuenta puente, sin línea propia por partner)."
        ),
    )
    x_summarized_move_count = fields.Integer(
        string="Comprobantes Resumidos",
        compute="_compute_x_summarized_move_count",
        help=(
            "Cantidad de comprobantes originales que este asiento (neteo "
            "operativo o resumen legal) absorbió en el Asistente de Cierre "
            "Mensual."
        ),
    )

    def _compute_x_summarized_move_count(self):
        for move in self:
            move.x_summarized_move_count = self.search_count(
                move._ivess_summarized_moves_domain()
            )

    def _ivess_summarized_moves_domain(self):
        self.ensure_one()
        return [
            "|",
            ("x_closed_by_summary_move_id", "=", self.id),
            ("line_ids.x_summary_move_id", "=", self.id),
        ]

    def action_view_summarized_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Comprobantes Resumidos"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": self._ivess_summarized_moves_domain(),
        }

    def action_view_closing_summary_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.x_closed_by_summary_move_id.id,
            "view_mode": "form",
        }

    @api.depends("x_closed_by_summary_move_id")
    def _compute_status_in_payment(self):
        super()._compute_status_in_payment()
        # La vista de lista de facturas usa este campo (no payment_state
        # directamente) para pintar el badge "Estado". Un comprobante
        # cerrado por resumen no debe seguir mostrando "Pagado"/"Cobrado":
        # su estado de pago real ahora se gestiona desde el asiento legal.
        for move in self:
            if move.x_closed_by_summary_move_id:
                move.status_in_payment = "x_closed_by_summary"

    @api.depends("line_ids.x_summary_move_id")
    def _compute_payments_widget_reconciled_info(self):
        super()._compute_payments_widget_reconciled_info()
        # El widget "Pagado el ..." se arma con TODA reconciliación contra
        # la línea de deuda, sin distinguir un cobro/pago real de la
        # reconciliación técnica contra el neteo del Asistente de Cierre
        # Mensual. Un comprobante recién cerrado por resumen (nunca cobrado)
        # no debe aparecer como "Pagado el <fecha del neteo>".
        for move in self:
            widget = move.invoice_payments_widget
            if not widget:
                continue
            content = [
                entry
                for entry in widget["content"]
                if not self.browse(entry["move_id"]).x_is_summary_entry
            ]
            move.invoice_payments_widget = {**widget, "content": content} if content else False

    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == "form":
            # l10n_ar_eynes agrega sus propios ribbons "COBRADO"/"PAGADO"
            # (payment_state == 'paid') sobre este mismo form. No se pueden
            # tocar por herencia XML normal: esa vista arrastra referencias
            # a campos de otros módulos AFIP que en este árbol de módulos
            # rompen la validación de vistas nuevas que la hereden. Se
            # parchea acá, sobre el arch ya resuelto, para que un
            # comprobante "cerrado por resumen" no siga mostrando esos
            # ribbons como si hubiera sido cobrado/pagado de verdad.
            for node in arch.xpath(
                "//widget[@name='web_ribbon' and (@title='COBRADO' or @title='PAGADO')]"
            ):
                invisible = node.get("invisible") or "0"
                if "x_closed_by_summary_move_id" not in invisible:
                    node.set("invisible", f"({invisible}) or x_closed_by_summary_move_id")
        return arch, view

    def _ivess_renumber_legal_folio(self, company):
        """Renumera x_folio_legal sin huecos para los diarios legales de `company`.

        Recalcula desde cero, en orden de fecha, la numeración de TODOS los
        asientos posteados de los diarios marcados x_is_legal_journal. Al
        ser un recálculo completo e idempotente, nunca deja huecos ni
        saltos, sin importar cuántas veces se ejecute ni qué haya pasado
        en los diarios operativos.
        """
        moves = self.search(
            [
                ("company_id", "=", company.id),
                ("journal_id.x_is_legal_journal", "=", True),
                ("state", "=", "posted"),
            ],
            order="date asc, id asc",
        )
        for index, move in enumerate(moves, start=1):
            folio = f"{index:06d}"
            if move.x_folio_legal != folio:
                move.x_folio_legal = folio
        return moves
