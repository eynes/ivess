import logging
import time
import traceback

from psycopg2 import errors as pg_errors

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module

_logger = logging.getLogger(__name__)

ACTIVE_STATES = ("queued", "closing", "building", "posting", "marking")


class AccountSummaryJob(models.Model):
    """Cierre Mensual que se procesa en segundo plano, por tandas.

    Un cierre con decenas de miles de apuntes no entra en un pedido web. El
    asistente lo encola acá y un cron lo avanza en tandas, cada una en su
    propia transacción (con commit): si algo falla queda el motivo y se puede
    reintentar sin repetir lo ya hecho, porque cada apunte neteado queda marcado
    (x_summary_move_id) y la tanda siguiente solo toma los que faltan.

    Etapas: neteo por tandas -> armado del asiento resumen legal por partes ->
    publicación -> marca de los comprobantes cerrados por partes.
    """

    _name = "ivess.accounting.summary.job"
    _inherit = ["mail.thread", "ivess.accounting.summary.engine"]
    _description = "Cierre Mensual en Segundo Plano"
    _order = "id desc"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    date_from = fields.Date(string="Desde", required=True, readonly=True)
    date_to = fields.Date(string="Hasta", required=True, readonly=True)
    operational_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="ivess_summary_job_journal_rel",
        column1="job_id",
        column2="journal_id",
        string="Diarios Operativos",
        readonly=True,
    )
    legal_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de Refundición (Legal)",
        required=True,
        readonly=True,
    )
    summary_move_date = fields.Date(string="Fecha del Asiento Resumen", readonly=True)
    summary_move_ref = fields.Char(string="Referencia del Asiento Resumen", readonly=True)
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Solicitado por",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("queued", "En cola"),
            ("closing", "Neteando por tandas"),
            ("building", "Armando el asiento resumen"),
            ("posting", "Publicando el asiento resumen"),
            ("marking", "Marcando comprobantes cerrados"),
            ("done", "Terminado"),
            ("error", "Con error"),
        ],
        string="Estado",
        default="queued",
        required=True,
        readonly=True,
        tracking=True,
    )
    retry_state = fields.Char(
        string="Etapa a reintentar",
        readonly=True,
        help="Etapa en la que quedó el trabajo cuando falló.",
    )
    snapshot_line_id = fields.Integer(
        string="Último apunte incluido",
        readonly=True,
        help=(
            "El cierre toma los apuntes que existían al pedirlo: los que se "
            "publiquen mientras corre quedan para el próximo cierre."
        ),
    )
    total_lines = fields.Integer(string="Apuntes a resumir", readonly=True)
    processed_lines = fields.Integer(string="Apuntes procesados", readonly=True)
    progress = fields.Float(string="Avance (%)", compute="_compute_progress")
    chunks_done = fields.Integer(string="Tandas hechas", readonly=True)
    legal_last_debt_id = fields.Integer(readonly=True)
    closed_last_id = fields.Integer(readonly=True)
    post_attempts = fields.Integer(string="Intentos de publicación", readonly=True)
    error_message = fields.Text(string="Motivo del error", readonly=True)
    started_at = fields.Datetime(string="Inicio", readonly=True)
    finished_at = fields.Datetime(string="Fin", readonly=True)
    netting_move_ids = fields.Many2many(
        comodel_name="account.move",
        relation="ivess_summary_job_netting_rel",
        column1="job_id",
        column2="move_id",
        string="Asientos de Neteo (Operativos)",
        readonly=True,
    )
    summary_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento Resumen (Legal)",
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="ivess.accounting.summary.job.line",
        inverse_name="job_id",
        string="Detalle para el asiento resumen",
        readonly=True,
    )

    @api.depends("processed_lines", "total_lines", "state")
    def _compute_progress(self):
        for job in self:
            if job.state == "done":
                job.progress = 100.0
            elif job.total_lines:
                # El neteo es lo más largo: se reserva el 10 % final para
                # armar, publicar y marcar.
                job.progress = min(job.processed_lines / job.total_lines, 1.0) * 90.0
            else:
                job.progress = 0.0

    @api.depends("date_from", "date_to", "company_id")
    def _compute_display_name(self):
        for job in self:
            job.display_name = _(
                "Cierre %(desde)s a %(hasta)s (%(compania)s)",
                desde=job.date_from,
                hasta=job.date_to,
                compania=job.company_id.name,
            )

    # ------------------------------------------------------------------
    # Alta y control de solapamientos
    # ------------------------------------------------------------------
    @api.model
    def _summary_check_no_active_job(self, company, journals, date_from, date_to):
        overlapping = self.search(
            [
                ("company_id", "=", company.id),
                ("state", "in", ACTIVE_STATES + ("error",)),
                ("operational_journal_ids", "in", journals.ids),
                ("date_from", "<=", date_to),
                ("date_to", ">=", date_from),
            ],
            limit=1,
        )
        if overlapping:
            raise UserError(
                _(
                    "Ya hay un cierre en segundo plano sin terminar que toca esos "
                    "diarios y fechas (%s). Esperá a que termine o resolvelo "
                    "antes de generar otro."
                )
                % overlapping.display_name
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            journals = self.env["account.journal"].browse(
                vals["operational_journal_ids"][0][2]
                if vals.get("operational_journal_ids")
                else []
            )
            self._summary_check_no_active_job(
                self.env["res.company"].browse(vals["company_id"]),
                journals,
                vals["date_from"],
                vals["date_to"],
            )
        return super().create(vals_list)

    def _schedule(self):
        """Pide al cron que arranque ya, sin esperar a su próximo horario."""
        cron = self.env.ref(
            "ivess_accounting_summary.ir_cron_summary_jobs", raise_if_not_found=False
        )
        if cron:
            cron.sudo()._trigger()

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_jobs(self):
        deadline = time.monotonic() + self._summary_param("cron_time_budget", 45)
        pending = False
        for job in self.search([("state", "in", ACTIVE_STATES)], order="id"):
            if time.monotonic() >= deadline:
                pending = True
                break
            if not job._try_lock():
                continue
            job._process(deadline)
            if job.state in ACTIVE_STATES:
                pending = True
        if pending:
            self._schedule()

    def _try_lock(self):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT 1 FROM ivess_accounting_summary_job WHERE id = %s "
                    "FOR UPDATE NOWAIT",
                    (self.id,),
                )
            return True
        except pg_errors.LockNotAvailable:
            return False

    def _commit(self):
        """Confirma lo hecho hasta acá. En los tests de Odoo no se puede
        confirmar el cursor: solo se vuelca a la base de la transacción."""
        if odoo_module.current_test:
            self.env.flush_all()
        else:
            self.env.cr.commit()

    def _process(self, deadline):
        self.ensure_one()
        job_id = self.id
        state_before = self.state
        try:
            job = self.with_user(self.user_id).with_context(
                allowed_company_ids=[self.company_id.id]
            )
            if job.state == "queued":
                job._start()
            if job.state == "closing":
                job._step_closing(deadline)
            if job.state == "building" and time.monotonic() < deadline:
                job._step_building(deadline)
            if job.state == "posting" and time.monotonic() < deadline:
                job._step_posting()
            if job.state == "marking" and time.monotonic() < deadline:
                job._step_marking(deadline)
        except Exception as exc:  # noqa: BLE001 - se informa y se reintenta a mano
            # Cada unidad de trabajo corre en un savepoint: lo que falló ya se
            # revirtió y lo confirmado antes de la falla queda.
            self.env.invalidate_all()
            job = self.browse(job_id)
            message = (
                str(exc)
                if isinstance(exc, UserError)
                else traceback.format_exc()[-3000:]
            )
            _logger.exception("Cierre mensual %s: error", job.display_name)
            job.sudo().write(
                {
                    "state": "error",
                    "retry_state": job.state if job.state in ACTIVE_STATES else state_before,
                    "error_message": message,
                }
            )
            job.sudo().message_post(
                body=_("El cierre se detuvo con un error: %s", message[:500]),
                partner_ids=job.user_id.partner_id.ids,
            )
            self._commit()

    # ------------------------------------------------------------------
    # Etapas (cada unidad de trabajo, en su savepoint y con su commit)
    # ------------------------------------------------------------------
    def _start(self):
        with self.env.cr.savepoint():
            self.write({"state": "closing", "started_at": fields.Datetime.now()})
        self._commit()

    def _next_chunk(self, chunk_size):
        """Próximas líneas a netear, siempre con TODAS las líneas de cada
        asiento (un neteo parcial de un asiento quedaría desbalanceado)."""
        domain = [("id", "<=", self.snapshot_line_id)]
        lines = self._summary_candidate_lines(
            extra_domain=domain, order="move_id, id", limit=chunk_size
        )
        if not lines:
            return lines
        last_move = lines[-1].move_id
        rest = self._summary_candidate_lines(
            extra_domain=domain + [("move_id", "=", last_move.id), ("id", "not in", lines.ids)]
        )
        return lines | rest

    def _step_closing(self, deadline):
        chunk_size = self._summary_param("chunk_lines", 500)
        while True:
            finished = False
            with self.env.cr.savepoint():
                lines = self._next_chunk(chunk_size)
                if not lines:
                    self.state = "building"
                    finished = True
                else:
                    number = self.chunks_done + 1
                    contrib = self._summary_close_lines(
                        lines, label_suffix=_(" (lote %s)", number)
                    )
                    self._store_contrib(contrib)
                    self.write(
                        {
                            "chunks_done": number,
                            "processed_lines": self.processed_lines + len(lines),
                            "netting_move_ids": [
                                (4, move_id) for move_id in contrib["netting_moves"].ids
                            ],
                        }
                    )
            self._commit()
            if finished or time.monotonic() >= deadline:
                return

    def _store_contrib(self, contrib):
        Line = self.env["ivess.accounting.summary.job.line"]
        rows = []
        for account_id, balance in contrib["pl"].items():
            rows.append({"kind": "pl", "account_id": account_id, "amount": balance})
        for account_id, entry in contrib["bridge"].items():
            rows.append(
                {
                    "kind": "bridge",
                    "account_id": account_id,
                    "amount": entry["amount"],
                    "payable": entry["payable"],
                }
            )
        for item in contrib["debt"]:
            rows.append(
                {
                    "kind": "debt",
                    "account_id": item["account_id"],
                    "partner_id": item["partner_id"],
                    "origin_move_id": item["origin_id"],
                    "name": item["name"],
                    "amount": item["residual"],
                }
            )
        for move_id in contrib["closed_move_ids"]:
            rows.append({"kind": "closed", "origin_move_id": move_id})
        Line.create([dict(row, job_id=self.id) for row in rows])

    def _debt_dicts(self, rows):
        return [
            {
                "account_id": row.account_id.id,
                "partner_id": row.partner_id.id,
                "origin_id": row.origin_move_id.id,
                "name": row.name,
                "residual": row.amount,
            }
            for row in rows
        ]

    def _step_building(self, deadline):
        Line = self.env["ivess.accounting.summary.job.line"]
        slice_size = self._summary_param("legal_slice_lines", 2000)
        Move = self.env["account.move"].with_context(check_move_validity=False)
        if not self.summary_move_id:
            with self.env.cr.savepoint():
                pl, bridge = {}, {}
                for row in Line.search([("job_id", "=", self.id), ("kind", "=", "pl")]):
                    pl[row.account_id.id] = pl.get(row.account_id.id, 0.0) + row.amount
                for row in Line.search([("job_id", "=", self.id), ("kind", "=", "bridge")]):
                    entry = bridge.setdefault(
                        row.account_id.id, {"amount": 0.0, "payable": False}
                    )
                    entry["amount"] += row.amount
                    entry["payable"] = entry["payable"] or row.payable
                first = Line.search(
                    [("job_id", "=", self.id), ("kind", "=", "debt")],
                    order="id",
                    limit=slice_size,
                )
                vals = self._summary_legal_line_vals(pl, bridge, [], only_totals=True)
                vals += self._summary_legal_line_vals(
                    {}, {}, self._debt_dicts(first), only_debt=True
                )
                if not vals:
                    raise UserError(
                        _("No hay montos para resumir en el período seleccionado.")
                    )
                move = Move.create(self._summary_move_vals(vals))
                self.write(
                    {
                        "summary_move_id": move.id,
                        "legal_last_debt_id": first[-1].id if first else 0,
                    }
                )
            self._commit()
        while time.monotonic() < deadline:
            with self.env.cr.savepoint():
                rows = Line.search(
                    [
                        ("job_id", "=", self.id),
                        ("kind", "=", "debt"),
                        ("id", ">", self.legal_last_debt_id),
                    ],
                    order="id",
                    limit=slice_size,
                )
                if rows:
                    Move.browse(self.summary_move_id.id).write(
                        {
                            "line_ids": self._summary_legal_line_vals(
                                {}, {}, self._debt_dicts(rows), only_debt=True
                            )
                        }
                    )
                    self.legal_last_debt_id = rows[-1].id
                else:
                    self.state = "posting"
            self._commit()
            if not rows:
                return

    def _step_posting(self):
        if self.post_attempts >= 3:
            raise UserError(
                _(
                    "El asiento resumen no se pudo publicar en 3 intentos "
                    "(probablemente supera el tiempo máximo de ejecución del "
                    "servidor). Pedí a soporte que suba el límite de los "
                    "procesos programados y reintentá."
                )
            )
        # Se cuenta el intento antes de publicar: si el servidor corta el
        # proceso por tiempo, el próximo ciclo sabe que ya se intentó.
        with self.env.cr.savepoint():
            self.post_attempts += 1
        self._commit()
        with self.env.cr.savepoint():
            self.summary_move_id.action_post()
            self.state = "marking"
        self._commit()

    def _step_marking(self, deadline):
        Line = self.env["ivess.accounting.summary.job.line"]
        slice_size = self._summary_param("mark_slice_moves", 2000)
        while True:
            with self.env.cr.savepoint():
                rows = Line.search(
                    [
                        ("job_id", "=", self.id),
                        ("kind", "=", "closed"),
                        ("id", ">", self.closed_last_id),
                    ],
                    order="id",
                    limit=slice_size,
                )
                if rows:
                    self._summary_mark(
                        rows.origin_move_id,
                        "x_closed_by_summary_move_id",
                        self.summary_move_id,
                    )
                    self.closed_last_id = rows[-1].id
                else:
                    self.write({"state": "done", "finished_at": fields.Datetime.now()})
                    self.message_post(
                        body=_(
                            "El cierre terminó: %(movimientos)s apuntes resumidos en el asiento %(asiento)s.",
                            movimientos=self.processed_lines,
                            asiento=self.summary_move_id.display_name,
                        ),
                        partner_ids=self.user_id.partner_id.ids,
                    )
            self._commit()
            if not rows or time.monotonic() >= deadline:
                return

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_retry(self):
        for job in self:
            if job.state != "error":
                raise UserError(_("Solo se reintenta un cierre con error."))
            job.write(
                {
                    "state": job.retry_state or "queued",
                    "error_message": False,
                    "post_attempts": 0,
                }
            )
            job._schedule()

    def action_view_summary_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.summary_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_netting_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Asientos de Neteo"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.netting_move_ids.ids)],
        }


class AccountSummaryJobLine(models.Model):
    """Lo que cada tanda aporta al asiento resumen legal. Se guarda para armar
    el asiento al final (los saldos pendientes hay que leerlos ANTES de
    conciliar) y queda como respaldo de auditoría del cierre."""

    _name = "ivess.accounting.summary.job.line"
    _description = "Detalle de Cierre Mensual en Segundo Plano"
    _order = "id"

    job_id = fields.Many2one(
        comodel_name="ivess.accounting.summary.job",
        required=True,
        ondelete="cascade",
        index=True,
    )
    kind = fields.Selection(
        selection=[
            ("pl", "Resultado / impuesto"),
            ("bridge", "Cuenta puente"),
            ("debt", "Deuda abierta"),
            ("closed", "Comprobante cerrado"),
        ],
        required=True,
        index=True,
    )
    account_id = fields.Many2one(comodel_name="account.account")
    partner_id = fields.Many2one(comodel_name="res.partner")
    origin_move_id = fields.Many2one(comodel_name="account.move")
    name = fields.Char()
    amount = fields.Float()
    payable = fields.Boolean()
