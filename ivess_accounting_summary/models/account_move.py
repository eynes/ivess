from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError


class AccountMove(models.Model):
    _inherit = "account.move"

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
    x_is_legal_summary_entry = fields.Boolean(
        string="Es Asiento Resumen Legal",
        compute="_compute_x_is_legal_summary_entry",
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

    def _ivess_is_summarized(self):
        """True si el comprobante ya fue absorbido por un Cierre Mensual."""
        self.ensure_one()
        return bool(
            self.x_closed_by_summary_move_id
            or self.line_ids.filtered("x_summary_move_id")
        )

    def button_draft(self):
        # Volver a borrador un comprobante ya resumido dejaría el neteo
        # operativo y el asiento legal apuntando a un comprobante editable,
        # con la deuda duplicada o perdida entre ambos diarios.
        summarized = self.filtered(lambda move: move._ivess_is_summarized())
        if summarized:
            raise UserError(
                _(
                    "No se puede volver a borrador: el asiento se encuentra "
                    "resumido por un Cierre Mensual (Contabilidad "
                    "Resumida).\n\nAsientos: %s",
                    ", ".join(summarized.mapped("display_name")),
                )
            )
        return super().button_draft()

    # ------------------------------------------------------------------
    # Deshacer un Cierre Mensual
    # ------------------------------------------------------------------
    @api.depends("x_is_summary_entry", "journal_id.x_is_legal_journal")
    def _compute_x_is_legal_summary_entry(self):
        for move in self:
            move.x_is_legal_summary_entry = bool(
                move.x_is_summary_entry and move.journal_id.x_is_legal_journal
            )

    def _ivess_is_legal_summary_move(self):
        self.ensure_one()
        return bool(self.x_is_summary_entry and self.journal_id.x_is_legal_journal)

    def _ivess_summary_closed_moves(self):
        """Comprobantes que este asiento resumen legal absorbió."""
        self.ensure_one()
        return self.with_context(active_test=False).search(
            [("x_closed_by_summary_move_id", "=", self.id)]
        )

    def _ivess_summary_netting_moves(self):
        """Asientos de neteo (diarios operativos) de este cierre.

        El asiento legal no los referencia: se llega a ellos desde los
        apuntes de los comprobantes cerrados, que quedaron marcados con el
        neteo que los procesó (x_summary_move_id)."""
        self.ensure_one()
        lines = self.env["account.move.line"].search(
            [
                ("move_id", "in", self._ivess_summary_closed_moves().ids),
                ("x_summary_move_id", "!=", False),
            ]
        )
        return lines.x_summary_move_id

    def _ivess_check_can_undo_summary(self):
        self.ensure_one()
        if self.x_folio_legal:
            raise UserError(
                _(
                    "No se puede deshacer el cierre: el asiento %s ya tiene "
                    "folio legal asignado (%s). Eliminarlo dejaría un hueco "
                    "en la numeración correlativa del libro diario.",
                    self.display_name,
                    self.x_folio_legal,
                )
            )
        if self.line_ids.matched_debit_ids or self.line_ids.matched_credit_ids:
            raise UserError(
                _(
                    "No se puede deshacer el cierre: el asiento %s tiene "
                    "cobros o pagos aplicados sobre sus líneas de deuda. "
                    "Desconciliá esos pagos primero.",
                    self.display_name,
                )
            )

    def _ivess_undo_summary_netting(self, netting_moves, closed_moves):
        """Deja los comprobantes como estaban antes del cierre: desconcilia
        y elimina los neteos y limpia las marcas que impedían volver a
        resumirlos."""
        cr = self.env.cr
        # Primero las marcas, después la desconciliación: así Odoo recalcula
        # el estado de pago de los comprobantes ya sin "Cerrado por Resumen".
        if netting_moves:
            cr.execute(
                "UPDATE account_move_line SET x_summary_move_id = NULL "
                "WHERE x_summary_move_id = ANY(%s)",
                [netting_moves.ids],
            )
        if closed_moves:
            cr.execute(
                "UPDATE account_move SET x_closed_by_summary_move_id = NULL "
                "WHERE id = ANY(%s)",
                [closed_moves.ids],
            )
        self.env["account.move.line"].invalidate_model(["x_summary_move_id"])
        self.env["account.move"].invalidate_model(["x_closed_by_summary_move_id"])
        if netting_moves:
            netting_moves.line_ids.remove_move_reconcile()
            netting_moves.filtered(lambda m: m.state == "posted").button_draft()
            netting_moves.unlink()

    def _ivess_undo_summary_closing(self):
        for move in self:
            move._ivess_check_can_undo_summary()
            move._ivess_undo_summary_netting(
                move._ivess_summary_netting_moves(),
                move._ivess_summary_closed_moves(),
            )

    @api.model
    def _ivess_orphan_summary_netting_moves(self):
        """Neteos de cierres cuyo asiento resumen legal ya no existe (se
        borró antes de que el borrado deshiciera el cierre): sus comprobantes
        quedaron sin 'Cerrado por Resumen' pero con el neteo vigente."""
        netting = self.search(
            [
                ("x_is_summary_entry", "=", True),
                ("journal_id.x_is_legal_journal", "=", False),
            ]
        )
        orphans = self.browse()
        Line = self.env["account.move.line"]
        for move in netting:
            marked = Line.search([("x_summary_move_id", "=", move.id)])
            if not marked.move_id.x_closed_by_summary_move_id:
                orphans |= move
        return orphans

    @api.model
    def _ivess_undo_orphan_summary_closings(self):
        orphans = self._ivess_orphan_summary_netting_moves()
        self._ivess_undo_summary_netting(orphans, self.browse())
        return orphans.ids

    def _ivess_undo_summary_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deshacer Cierre Mensual"),
            "res_model": "ivess.undo.summary.closing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_undo_summary_closing(self):
        """Abre la confirmación con la cantidad de comprobantes y neteos que
        se van a revertir."""
        self.ensure_one()
        if not self._ivess_is_legal_summary_move():
            raise UserError(_("Solo se puede deshacer un asiento resumen del Diario Legal."))
        self._ivess_check_can_undo_summary()
        return self._ivess_undo_summary_wizard_action()

    def unlink(self):
        # Borrar el asiento resumen deshace el cierre: sin esto los
        # comprobantes quedan marcados como neteados y no se pueden volver
        # a resumir. Desde la pantalla se pasa por la confirmación con las
        # cantidades (RedirectWarning); el contexto ivess_undo_confirmed
        # indica que ya se confirmó.
        legal = self.filtered(lambda m: m._ivess_is_legal_summary_move())
        if (
            len(legal) == 1
            and not self.env.context.get("ivess_undo_confirmed")
            and (legal._ivess_summary_closed_moves() or legal._ivess_summary_netting_moves())
        ):
            legal._ivess_check_can_undo_summary()
            raise RedirectWarning(
                _(
                    "Eliminar el asiento %(move)s deshace el Cierre Mensual: se "
                    "revierten %(closed)s comprobantes y %(netting)s neteos de los "
                    "diarios operativos. Confirmá con «Deshacer cierre».",
                    move=legal.display_name,
                    closed=len(legal._ivess_summary_closed_moves()),
                    netting=len(legal._ivess_summary_netting_moves()),
                ),
                legal._ivess_undo_summary_wizard_action(),
                _("Deshacer cierre"),
            )
        legal._ivess_undo_summary_closing()
        return super().unlink()

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
        # El neteo del Asistente de Cierre Mensual reconcilia la línea de
        # deuda original contra el asiento legal para cerrarla
        # operativamente (evita que quede duplicada como pendiente en dos
        # lados). Eso dispara el cómputo nativo de Odoo, que ve
        # amount_residual=0 y lo marca "Pagado" — aunque nunca se cobró: el
        # saldo simplemente se trasladó a la cuenta de deuda legal. No se
        # inventa un estado nuevo: si el comprobante tenía saldo pendiente
        # al momento del cierre (queda trazado por x_origin_document_id en
        # el asiento legal), se lo deja como "Sin pagar" (valor nativo), en
        # vez de "Pagado". Si ya estaba cobrado/pagado de verdad ANTES del
        # cierre (fue por la cuenta puente, sin línea propia), no se toca:
        # ese "Pagado" es real.
        closed_moves = self.filtered("x_closed_by_summary_move_id")
        if not closed_moves:
            return
        # Comprobantes con deuda abierta, por asiento de cierre: una sola
        # consulta agrupada. Recorrer las líneas del asiento resumen por cada
        # comprobante es cuadrático (con decenas de miles de líneas no termina).
        origin_ids_by_closing = defaultdict(set)
        for closing_move, origin_move in self.env["account.move.line"]._read_group(
            [
                ("move_id", "in", closed_moves.x_closed_by_summary_move_id.ids),
                ("x_origin_document_id", "!=", False),
            ],
            ["move_id", "x_origin_document_id"],
        ):
            origin_ids_by_closing[closing_move.id].add(origin_move.id)
        for move in closed_moves:
            if move.id in origin_ids_by_closing[move.x_closed_by_summary_move_id.id]:
                move.status_in_payment = "not_paid"

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
        elif view_type in ("list", "tree") and arch.tag in ("list", "tree"):
            # Se agrega como columna opcional (oculta por defecto, elegible
            # desde el selector de columnas) en cualquier lista de
            # comprobantes: no reemplaza al "Estado" nativo, solo permite
            # ver de un vistazo cuáles ya fueron absorbidos por un cierre
            # mensual, sin depender de que el estado de pago lo refleje.
            if arch.find(".//field[@name='x_closed_by_summary_move_id']") is None:
                field_node = arch.makeelement(
                    "field",
                    {
                        "name": "x_closed_by_summary_move_id",
                        "string": "Cerrado por Resumen",
                        "optional": "hide",
                    },
                )
                arch.append(field_node)
        return arch, view

    @api.model
    def _ivess_get_summarized_payment_ids(self, company_ids):
        """Ids de cobros/pagos ya absorbidos por un Cierre Mensual.

        El cierre solo marca los comprobantes de los diarios operativos. El
        cobro/pago de un comprobante resumido vive en otro diario (banco,
        caja) y quedaría listado junto al asiento resumen, que ya lo
        incluye ("cobrado en el período" / puente). Se considera absorbido
        el asiento reconciliado contra un comprobante resumido con fecha
        igual o anterior a la del asiento resumen; uno posterior sigue
        visible porque no forma parte del resumen.
        """
        partials = self.env["account.partial.reconcile"].search(
            [
                ("company_id", "in", company_ids),
                "|",
                ("debit_move_id.move_id.x_closed_by_summary_move_id", "!=", False),
                ("credit_move_id.move_id.x_closed_by_summary_move_id", "!=", False),
            ]
        )
        move_ids = set()
        for partial in partials:
            debit_move = partial.debit_move_id.move_id
            credit_move = partial.credit_move_id.move_id
            for document, other in (
                (debit_move, credit_move),
                (credit_move, debit_move),
            ):
                closing = document.x_closed_by_summary_move_id
                if (
                    closing
                    and not other.x_closed_by_summary_move_id
                    and not other.x_is_summary_entry
                    and other.date <= closing.date
                ):
                    move_ids.add(other.id)
        return list(move_ids)

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
