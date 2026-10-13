import base64
import csv
import io
from datetime import datetime

import logging
import threading

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.service.server import cron_database_list

from .invoice_import_wizard import IvessInvoiceImportWizard

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None
_logger = logging.getLogger(__name__)

# La hoja "cobranzas" del formato "aguas" repite el header "letra" (y varias
# columnas más) en dos posiciones distintas (la del recibo y la de la
# factura asociada que cancela), por lo que no se puede indexar por nombre
# de columna como hace el import de facturas: se valida y se lee por
# posición fija.
EXPECTED_HEADERS = [
    "tipo de comprobante",
    "letra",
    "pto de vta",
    "num compr",
    "fecha",
    "cod cliente",
    "importe total",
    "comprobante anulado?",
    "tipo de compr asoc",
    "letra",
    "pto de venta",
    "numero compr",
    "importe",
    "medio de pago",
    "moneda",
    "tipo de cambio",
    "caja",
    "importe del movimiento",
    "cod bco",
    "sucursal del bco",
    "importe del movimiento en moneda local",
]

# Columnas que identifican la cabecera del recibo agrupado (mismo criterio
# que GROUP_KEY_FIELDS de invoice_import_wizard.py).
GROUP_KEY_FIELDS = ("tipo_comprobante", "letra", "pto_vta", "num_compr")
HEADER_ONLY_FIELDS = ("fecha", "cod_cliente", "importe_total", "comprobante_anulado")
DETAIL_FIELDS = (
    "tipo_compr_asoc",
    "letra_asoc",
    "pto_venta_asoc",
    "numero_compr_asoc",
    "importe",
    "medio_pago",
    "moneda",
    "tipo_cambio",
    "caja",
    "importe_movimiento",
    "cod_bco",
    "sucursal_bco",
    "importe_movimiento_moneda_local",
)


def group_payment_rows(rows):
    """Agrupa renglones desnormalizados de cobranza (una fila por factura
    aplicada) en recibos (cabecera + líneas de aplicación), por
    (tipo_comprobante, letra, pto_vta, num_compr). Misma lógica que
    group_invoice_rows en invoice_import_wizard.py, adaptada a los campos
    de la hoja "cobranzas".
    """
    groups_by_key = {}
    ordered_groups = []

    for row in rows:
        missing = [f for f in GROUP_KEY_FIELDS if not row.get(f)]
        if missing:
            ordered_groups.append(
                {
                    "tipo_comprobante": row.get("tipo_comprobante") or "",
                    "letra": row.get("letra") or "",
                    "pto_vta": row.get("pto_vta") or "",
                    "num_compr": row.get("num_compr") or "",
                    "lines": [],
                    "row_numbers": [row.get("_row_number")],
                    "error": _("Fila %s: faltan datos de comprobante (%s).")
                    % (row.get("_row_number"), ", ".join(missing)),
                }
            )
            continue

        key = tuple(row[f] for f in GROUP_KEY_FIELDS)
        group = groups_by_key.get(key)
        if group is None:
            group = {f: row[f] for f in GROUP_KEY_FIELDS}
            for f in HEADER_ONLY_FIELDS:
                group[f] = row.get(f)
            group["lines"] = []
            group["row_numbers"] = []
            group["error"] = None
            groups_by_key[key] = group
            ordered_groups.append(group)

        group["row_numbers"].append(row.get("_row_number"))
        group["lines"].append({f: row.get(f) for f in DETAIL_FIELDS})

    return ordered_groups


class IvessPaymentImportWizard(models.TransientModel):
    _name = "ivess.payment.import.wizard"
    _description = "Importador de cobros de clientes desde archivo Excel"

    # Código de "medio de pago" que identifica efectivo/caja en el Excel.
    _CASH_MEDIO_PAGO = "1"

    file =fields.Binary(string="Archivo (.xlsx)", required=True)
    filename = fields.Char(string="Nombre de archivo")
    state = fields.Selection(
        [
            ("upload", "Subir archivo"),
            ("preview", "Previsualización"),
            ("processing", "Procesando"),
            ("interrupted", "Interrumpida"),
            ("done", "Resultado"),
        ],
        default="upload",
    )
    progress_total = fields.Integer(string="Recibos a procesar", readonly=True)
    progress_done = fields.Integer(string="Recibos procesados", readonly=True)
    last_heartbeat = fields.Datetime(
        string="Última señal de vida",
        readonly=True,
        help="Última vez que el proceso en segundo plano informó su avance.",
    )
    is_stalled = fields.Boolean(
        string="Sin señal de vida", compute="_compute_is_stalled"
    )
    process_error = fields.Text(string="Error del proceso", readonly=True)
    result_line_ids = fields.One2many(
        "ivess.payment.import.result.line",
        "wizard_id",
        string="Cobros",
    )
    total_count = fields.Integer(string="Total", readonly=True)
    ok_count = fields.Integer(string="OK", readonly=True)
    error_count = fields.Integer(string="Errores", readonly=True)
    skipped_count = fields.Integer(string="Anulados (no importados)", readonly=True)

    # ------------------------------------------------------------------
    # Paso 1 -> 2: leer archivo, agrupar y validar (no escribe account.payment)
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Adjuntá un archivo para importar."))
        if openpyxl is None:
            raise UserError(
                _(
                    "Falta la librería 'openpyxl' en el servidor para leer"
                    " archivos .xlsx."
                )
            )
        rows = self._read_excel_rows(base64.b64decode(self.file))
        groups = group_payment_rows(rows)
        # Ver _build_preview_cache: resuelve de una sola vez, contra todos
        # los grupos, los lookups que antes se repetían con un search()
        # propio por cada recibo/línea de aplicación.
        cache = self._build_preview_cache(groups)

        self.result_line_ids.unlink()
        vals_list = [
            self._prepare_preview_line_vals(index, group, cache)
            for index, group in enumerate(groups)
        ]
        if vals_list:
            self.env["ivess.payment.import.result.line"].create(vals_list)

        self.total_count = len(self.result_line_ids)
        self.error_count = len(self.result_line_ids.filtered("has_error"))
        self.skipped_count = len(
            self.result_line_ids.filtered(
                lambda r: not r.has_error and r.comprobante_anulado
            )
        )
        self.ok_count = self.total_count - self.error_count - self.skipped_count
        self.state = "preview"
        return self._reopen()

    def action_back_to_upload(self):
        self.ensure_one()
        self.result_line_ids.unlink()
        self.state = "upload"
        return self._reopen()

    def action_export_errors(self):
        self.ensure_one()
        lines = self.result_line_ids.filtered("has_error")
        if not lines:
            raise UserError(_("No hay errores para exportar."))
        attachment = self.env["ir.attachment"].create(
            {
                "name": "errores_import_cobros_%s.csv"
                % fields.Date.context_today(self),
                "type": "binary",
                "datas": base64.b64encode(self._build_errors_csv(lines)),
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    @staticmethod
    def _build_errors_csv(lines):
        # ';' como delimitador y BOM utf-8: mismo criterio que
        # IvessInvoiceImportWizard._build_errors_csv, para que lo abra bien
        # Excel en configuración regional argentina.
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                _("Comprobante"),
                _("Código cliente"),
                _("Cliente"),
                _("Fecha"),
                _("Importe total"),
                _("Error"),
            ]
        )
        for line in lines:
            writer.writerow(
                [
                    line.comprobante_display,
                    line.cliente_codigo,
                    line.partner_id.display_name or "",
                    line.fecha or "",
                    line.importe_total,
                    (line.error_message or "").replace("\n", " | "),
                ]
            )
        return buffer.getvalue().encode("utf-8-sig")

    def _reopen(self):
        action = {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
        if self.state == "processing":
            # Vista liviana, sin la lista de recibos: la barra de progreso
            # la recarga cada pocos segundos.
            view = self.env.ref(
                "ivess_invoice_import.view_ivess_payment_import_wizard_progress"
            )
            action["views"] = [(view.id, "form")]
        return action

    def action_reopen(self):
        """Lo llama la barra de progreso cuando la carga terminó o se
        interrumpió, para volver a la vista completa."""
        self.ensure_one()
        if self.is_stalled:
            self.state = "interrupted"
        return self._reopen()

    # ------------------------------------------------------------------
    # Lectura y parseo del Excel
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_header(value):
        return (value or "").strip().lower()

    @staticmethod
    def _to_str(value):
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _to_float(value):
        # Los importes de "aguas" vienen como texto con ceros a la izquierda
        # y coma decimal (ej. "000000028016,00"): si hay coma, es el
        # separador decimal y los puntos son de miles.
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        return float(text)

    @staticmethod
    def _to_date(value):
        text = str(int(value)) if isinstance(value, float) else str(value).strip()
        return datetime.strptime(text, "%Y%m%d").date()

    @staticmethod
    def _get_sheet(workbook):
        for name in workbook.sheetnames:
            if name.strip().lower() == "cobranzas":
                return workbook[name]
        return workbook.worksheets[0]

    def _read_excel_rows(self, content):
        try:
            # read_only=True: lectura en modo streaming, ver el mismo
            # comentario en IvessInvoiceImportWizard._read_excel_rows.
            workbook = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            raise UserError(
                _("No se pudo leer el archivo como Excel: %s") % exc
            ) from exc

        sheet = self._get_sheet(workbook)
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            raise UserError(_("La hoja '%s' del archivo está vacía.") % sheet.title)

        headers = [self._normalize_header(h) for h in header_row]
        mismatches = [
            _("columna %d: se esperaba '%s', se encontró '%s'")
            % (i + 1, expected, headers[i] if i < len(headers) else "")
            for i, expected in enumerate(EXPECTED_HEADERS)
            if (headers[i] if i < len(headers) else "") != expected
        ]
        if mismatches:
            raise UserError(
                _(
                    "El formato de columnas de la hoja '%s' no coincide con"
                    " el esperado:\n%s"
                )
                % (sheet.title, "\n".join(mismatches))
            )

        rows = []
        for row_number, raw_row in enumerate(
            sheet.iter_rows(min_row=2, values_only=True), start=2
        ):
            if all(cell is None for cell in raw_row):
                continue
            rows.append(self._row_to_dict(raw_row, row_number))
        return rows

    def _row_to_dict(self, raw_row, row_number):
        def cell(index):
            return raw_row[index] if index < len(raw_row) else None

        return {
            "_row_number": row_number,
            "tipo_comprobante": self._to_str(cell(0)).upper(),
            "letra": self._to_str(cell(1)).upper(),
            "pto_vta": self._to_str(cell(2)),
            "num_compr": self._to_str(cell(3)),
            "fecha": cell(4),
            "cod_cliente": self._to_str(cell(5)),
            "importe_total": cell(6),
            "comprobante_anulado": self._to_str(cell(7)).upper() == "S",
            "tipo_compr_asoc": self._to_str(cell(8)).upper(),
            "letra_asoc": self._to_str(cell(9)).upper(),
            "pto_venta_asoc": self._to_str(cell(10)),
            "numero_compr_asoc": self._to_str(cell(11)),
            "importe": cell(12),
            "medio_pago": self._to_str(cell(13)),
            "moneda": self._to_str(cell(14)),
            "tipo_cambio": self._to_str(cell(15)),
            "caja": self._to_str(cell(16)),
            "importe_movimiento": cell(17),
            "cod_bco": self._to_str(cell(18)),
            "sucursal_bco": self._to_str(cell(19)),
            "importe_movimiento_moneda_local": cell(20),
        }

    # ------------------------------------------------------------------
    # Cache de lookups para la previsualización: mismo criterio que
    # IvessInvoiceImportWizard._build_preview_cache (ver comentario ahí):
    # reemplaza los search() repetidos por recibo/línea de aplicación por
    # un puñado de búsquedas en lote sobre todo el archivo.
    # ------------------------------------------------------------------

    def _build_preview_cache(self, groups):
        invoice_refs = set()
        for group in groups:
            if group.get("error"):
                continue
            for line in group["lines"]:
                if line["tipo_compr_asoc"] == "FC":
                    invoice_refs.add(
                        IvessInvoiceImportWizard._comprobante_ref(
                            line["letra_asoc"],
                            line["pto_venta_asoc"],
                            line["numero_compr_asoc"],
                        )
                    )

        invoice_by_ref = {}
        if invoice_refs:
            for move in self.env["account.move"].search(
                [("move_type", "=", "out_invoice"), ("ref", "in", list(invoice_refs))]
            ):
                invoice_by_ref.setdefault(move.ref, move)

        payment_mode_by_key = {}
        for mapping in self.env["ivess.payment.import.payment.method.code"].search(
            [("company_id", "=", self.env.company.id)]
        ):
            # Si es caja no lleva banco ni sucursal: se ignoran aunque el
            # mapeo los tenga cargados (el onchange del diario los
            # autocompletaba desde la cuenta bancaria).
            is_cash = mapping.medio_pago == self._CASH_MEDIO_PAGO
            # Los campos Char vacíos se guardan como NULL (False): se
            # normalizan a '' para que la clave coincida con la del archivo.
            key = (
                mapping.medio_pago,
                mapping.caja or "",
                "" if is_cash else self._norm_bank_code(mapping.cod_bco),
                "" if is_cash else (mapping.sucursal_bco or ""),
            )
            payment_mode_by_key.setdefault(key, mapping.journal_id)

        receipt_journal_by_pos = self._find_receipt_journals_by_pos(groups)

        cod_clientes = {g["cod_cliente"] for g in groups if g.get("cod_cliente")}
        partner_by_bejerman = {}
        if cod_clientes:
            # Solo clientes de la compañía activa (o compartidos): un
            # cliente de otra compañía no se puede usar en el recibo.
            for partner in self.env["res.partner"].search(
                [
                    ("codigo_bejerman", "in", list(cod_clientes)),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", self.env.company.id),
                ]
            ):
                partner_by_bejerman[partner.codigo_bejerman] = (
                    partner_by_bejerman.get(
                        partner.codigo_bejerman, self.env["res.partner"]
                    )
                    | partner
                )

        # detail_results se calcula una sola vez por grupo (resuelve todas
        # las líneas de aplicación contra los caches de arriba) y se
        # reutiliza tanto para el prefetch de deduplicación de abajo como
        # para el vals final en _prepare_preview_line_vals: evita repetir
        # la misma resolución dos veces.
        detail_results = {}
        for index, group in enumerate(groups):
            if group.get("error"):
                continue
            detail_results[index] = self._resolve_detail_lines(
                group["lines"], invoice_by_ref, payment_mode_by_key
            )

        partner_results = {}
        for index, group in enumerate(groups):
            if group.get("error"):
                continue
            partner_results[index] = self._resolve_partner(
                group, detail_results[index][2], partner_by_bejerman
            )

        dedup_keys = set()
        for index, group in enumerate(groups):
            if group.get("error") or group["comprobante_anulado"]:
                continue
            partner = partner_results[index][0]
            if not partner:
                continue
            ref = IvessInvoiceImportWizard._comprobante_ref(
                group["letra"], group["pto_vta"], group["num_compr"]
            )
            dedup_keys.add((ref, partner.id))

        orders_by_key = {}
        if dedup_keys:
            refs = {k[0] for k in dedup_keys}
            partner_ids = {k[1] for k in dedup_keys}
            for order in self.env["account.payment.order"].search(
                [
                    ("type", "=", "receipt"),
                    ("reference", "in", list(refs)),
                    ("partner_id", "in", list(partner_ids)),
                ]
            ):
                okey = (order.reference, order.partner_id.id)
                orders_by_key[okey] = (
                    orders_by_key.get(okey, self.env["account.payment.order"]) | order
                )

        return {
            "receipt_journal_by_pos": receipt_journal_by_pos,
            "detail_results": detail_results,
            "partner_results": partner_results,
            "orders_by_key": orders_by_key,
        }

    # ------------------------------------------------------------------
    # Resolución de cada grupo contra Odoo (cliente vía la factura que
    # cancela cada línea de aplicación) y armado de los vals de la línea de
    # previsualización (se crean todas juntas en lote, ver action_preview).
    # ------------------------------------------------------------------

    def _prepare_preview_line_vals(self, index, group, cache):
        if group.get("error"):
            return {
                "wizard_id": self.id,
                "tipo_comprobante": group["tipo_comprobante"],
                "letra": group["letra"],
                "pto_vta": group["pto_vta"],
                "numero_comprobante": group["num_compr"],
                "has_error": True,
                "error_message": group["error"],
            }

        errors = []
        if group["tipo_comprobante"] != "RMP":
            errors.append(
                _(
                    "tipo de comprobante '%s' no soportado (esta versión solo"
                    " importa 'RMP')."
                )
                % group["tipo_comprobante"]
            )

        try:
            fecha = self._to_date(group["fecha"]) if group["fecha"] else False
        except ValueError:
            fecha = False
            errors.append(_("Fecha inválida: '%s'.") % group["fecha"])

        try:
            importe_total = self._to_float(group["importe_total"])
        except (TypeError, ValueError):
            importe_total = 0.0
            errors.append(_("Importe total inválido: '%s'.") % group["importe_total"])

        comprobante_ref = IvessInvoiceImportWizard._comprobante_ref(
            group["letra"], group["pto_vta"], group["num_compr"]
        )

        journal, journal_candidates = cache["receipt_journal_by_pos"][group["pto_vta"]]
        if not journal:
            if journal_candidates:
                errors.append(
                    _(
                        "El punto de venta '%(pos)s' coincide con %(count)s"
                        " diarios de tipo 'Recibo de Cobranza'; debe coincidir"
                        " con uno solo."
                    )
                    % {"pos": group["pto_vta"], "count": journal_candidates}
                )
            else:
                errors.append(
                    _(
                        "No se encontró un diario de tipo 'Recibo de Cobranza'"
                        " (account.journal type='receipt') para el punto de"
                        " venta '%s'."
                    )
                    % group["pto_vta"]
                )

        if journal and not group["comprobante_anulado"]:
            period_error = self._check_journal_period(journal, fecha)
            if period_error:
                errors.append(period_error)

        detail_vals, detail_errors, _matched_partners, applied_total = cache[
            "detail_results"
        ][index]
        errors.extend(detail_errors)

        partner, partner_error = cache["partner_results"][index]
        if partner_error:
            errors.append(partner_error)

        if not errors and abs(applied_total - importe_total) > 0.01:
            errors.append(
                _(
                    "La suma de los importes del recibo (%.2f) no coincide con"
                    " el importe total del recibo (%.2f)."
                )
                % (applied_total, importe_total)
            )

        if partner and not group["comprobante_anulado"]:
            candidates = cache["orders_by_key"].get(
                (comprobante_ref, partner.id), self.env["account.payment.order"]
            )
            existing = candidates[:1]
            if existing:
                errors.append(
                    _(
                        "Ya existe un cobro importado con esta clave"
                        " (account.payment.order #%s)."
                    )
                    % existing.id
                )

        return {
            "wizard_id": self.id,
            "tipo_comprobante": group["tipo_comprobante"],
            "letra": group["letra"],
            "pto_vta": group["pto_vta"],
            "numero_comprobante": group["num_compr"],
            "comprobante_ref": comprobante_ref,
            "fecha": fecha,
            "importe_total": importe_total,
            "comprobante_anulado": bool(group["comprobante_anulado"]),
            "cliente_codigo": group["cod_cliente"],
            "partner_id": partner.id if partner else False,
            "journal_id": journal.id if journal else False,
            "has_error": bool(errors),
            "error_message": "\n".join(errors) if errors else False,
            "detail_line_ids": detail_vals,
        }

    def _find_receipt_journals_by_pos(self, groups):
        """Resuelve el diario de Recibo de Cobranza (account.journal con
        type='receipt') de la compañía activa para cada punto de venta
        distinto del archivo (columna "pto de vta" del recibo).

        Puede haber más de un diario 'receipt' (uno por punto de venta de
        cobranza): se matchea el punto de venta contra los dígitos del
        código del diario o, si no coincide, contra los dígitos de su
        nombre (mismo criterio que IvessInvoiceImportWizard._find_journal,
        sin filtrar por letra: account.journal.denomination no tiene un
        valor que represente la "X" de los recibos de "aguas"). Si ningún
        diario coincide pero la compañía tiene un único diario 'receipt',
        se usa ese (comportamiento anterior a la selección por punto de
        venta). Se resuelve una sola vez por punto de venta distinto.

        :return: dict pto_vta -> (diario o None, cantidad de diarios
            candidatos).
        """
        journals = self.env["account.journal"].search(
            [
                ("type", "=", "receipt"),
                ("company_id", "=", self.env.company.id),
            ]
        )
        digits_to_int = IvessInvoiceImportWizard._digits_to_int
        result = {}
        for pto_vta in {g["pto_vta"] for g in groups if not g.get("error")}:
            pos_number = digits_to_int(pto_vta)
            matches = journals.browse()
            if pos_number is not None:
                matches = journals.filtered(
                    lambda j, pos=pos_number: digits_to_int(j.code) == pos
                    or digits_to_int(j.name) == pos
                )
            if not matches and len(journals) == 1:
                matches = journals
            result[pto_vta] = (matches[0] if len(matches) == 1 else None, len(matches))
        return result

    def _check_journal_period(self, journal, fecha):
        """Replica la validación de ivess_validate_period.account.move._post
        (si ese módulo está instalado) para avisar en la previsualización y
        no recién al confirmar: allí, ante un período inválido, el módulo
        hace un commit() antes de lanzar el error, lo que deja el recibo a
        medio crear y destruye el savepoint de cada recibo.

        :return: mensaje de error o None.
        """
        if not hasattr(self.env["account.move"], "_validate_period"):
            return None
        if not journal.due_date:
            return _(
                "El diario '%s' no tiene fecha de cierre establecida"
                " (configurar en Contabilidad > Diarios > Actualizar períodos"
                " de diarios)."
            ) % (journal.display_name)
        if fecha and fecha < journal.due_date:
            return _(
                "La fecha del recibo (%s) es anterior a la fecha de cierre"
                " del diario '%s' (%s)."
            ) % (
                fecha.strftime("%d-%m-%Y"),
                journal.display_name,
                journal.due_date.strftime("%d-%m-%Y"),
            )
        return None

    def _recover_failed_receipt(self, result_lines):
        """Limpia lo que pudo quedar de uno o más recibos que fallaron
        después de que algún módulo hiciera commit() dentro de la
        transacción (ver _check_journal_period): rollback de la transacción
        abortada y baja de los recibos/asientos en borrador que ese commit
        dejó guardados."""
        self.env.cr.rollback()
        self.env.invalidate_all()
        references = result_lines.mapped("comprobante_ref")
        leftovers = self.env["account.payment.order"].search(
            [
                ("type", "=", "receipt"),
                ("state", "=", "draft"),
                ("reference", "in", references),
                ("partner_id", "in", result_lines.partner_id.ids),
            ]
        )
        if leftovers:
            leftovers.cancel_voucher()
            leftovers.unlink()
        # El asiento en borrador también quedó guardado por el commit, pero
        # puede no estar enlazado todavía al recibo (move_id no se escribió).
        draft_moves = self.env["account.move"].search(
            [
                ("move_type", "=", "entry"),
                ("state", "=", "draft"),
                ("ref", "in", references),
                ("journal_id", "in", result_lines.journal_id.ids),
            ]
        )
        if draft_moves:
            draft_moves.with_context(force_delete=True).unlink()
        self.env.cr.commit()  # pylint: disable=invalid-commit

    def _resolve_partner(self, group, matched_partners, partner_by_bejerman):
        """Resuelve el cliente del recibo.

        Si alguna línea aplica a una factura, el cliente sale de esas
        facturas (deben ser de un único cliente). Si el recibo no trae
        facturas asociadas (recibo a cuenta), sale de la columna "cod
        cliente" contra res.partner.codigo_bejerman.

        :return: tupla (cliente o False, mensaje de error o None).
        """
        has_invoice_lines = any(
            not self._is_on_account_line(line) for line in group["lines"]
        )
        if has_invoice_lines:
            if not matched_partners:
                return False, _(
                    "No se pudo determinar el cliente: ninguna factura"
                    " aplicada pudo resolverse."
                )
            if len(matched_partners) > 1:
                return False, _(
                    "El recibo aplica a facturas de más de un cliente"
                    " distinto (%s); no se puede determinar un único cliente."
                ) % ", ".join(sorted(p.display_name for p in matched_partners))
            return list(matched_partners)[0], None

        candidates = partner_by_bejerman.get(
            group["cod_cliente"], self.env["res.partner"]
        )
        if len(candidates) == 1:
            return candidates, None
        if candidates:
            return False, _(
                "El código de cliente '%s' coincide con %s clientes distintos."
            ) % (group["cod_cliente"], len(candidates))
        return False, _("No se encontró un cliente con código Bejerman '%s'.") % (
            group["cod_cliente"]
        )

    @staticmethod
    def _is_on_account_line(line):
        """Línea de recibo sin factura asociada (pago a cuenta)."""
        return not any(
            line.get(f)
            for f in (
                "tipo_compr_asoc",
                "letra_asoc",
                "pto_venta_asoc",
                "numero_compr_asoc",
            )
        )

    @staticmethod
    def _norm_bank_code(value):
        """Código de banco sin ceros a la izquierda: el archivo trae '017' y
        el mapeo puede tener '17' (o al revés)."""
        return (value or "").strip().lstrip("0")

    @staticmethod
    def _lookup_payment_mode(payment_mode_by_key, line):
        """Busca el diario mapeado para (medio de pago, caja, cod bco,
        sucursal). Si es caja (medio '1') no lleva banco ni sucursal. Para
        el resto, si no hay mapeo exacto se relaja primero la sucursal y
        después el código de banco (un mismo mapeo sirve para todos los
        bancos, ej. cheques de bancos distintos)."""
        medio_pago = line["medio_pago"]
        caja = line["caja"]
        if medio_pago == IvessPaymentImportWizard._CASH_MEDIO_PAGO:
            return payment_mode_by_key.get((medio_pago, caja, "", ""))
        cod_bco = IvessPaymentImportWizard._norm_bank_code(line["cod_bco"])
        for cod_bco_try, sucursal_bco in (
            (cod_bco, line["sucursal_bco"]),
            (cod_bco, ""),
            ("", ""),
        ):
            mode = payment_mode_by_key.get(
                (medio_pago, caja, cod_bco_try, sucursal_bco)
            )
            if mode:
                return mode
        return None

    def _resolve_detail_lines(self, lines, invoice_by_ref, payment_mode_by_key):
        detail_vals = []
        errors = []
        matched_partners = set()
        applied_total = 0.0

        if not lines:
            errors.append(_("El recibo no tiene líneas."))
            return detail_vals, errors, matched_partners, applied_total

        for line in lines:
            line_errors = []
            on_account = self._is_on_account_line(line)

            if on_account:
                # Recibo sin factura asociada (pago a cuenta): no hay
                # columna "importe" aplicado, el monto es el del movimiento
                # (en moneda local).
                amount_cell = (
                    line["importe_movimiento_moneda_local"]
                    if line["importe_movimiento_moneda_local"] is not None
                    else line["importe_movimiento"]
                )
                try:
                    importe = self._to_float(amount_cell)
                    if importe <= 0:
                        raise ValueError
                    applied_total += importe
                except (TypeError, ValueError):
                    importe = 0.0
                    line_errors.append(
                        _("El recibo no informa un importe del movimiento válido.")
                    )
            else:
                try:
                    importe = self._to_float(line["importe"])
                except (TypeError, ValueError):
                    importe = 0.0
                    line_errors.append(_("Importe inválido: '%s'.") % line["importe"])

            invoice = self.env["account.move"]
            if on_account:
                pass
            elif line["tipo_compr_asoc"] != "FC":
                line_errors.append(
                    _("tipo de comprobante asociado '%s' no soportado (solo 'FC').")
                    % line["tipo_compr_asoc"]
                )
            else:
                invoice_ref = IvessInvoiceImportWizard._comprobante_ref(
                    line["letra_asoc"],
                    line["pto_venta_asoc"],
                    line["numero_compr_asoc"],
                )
                invoice = invoice_by_ref.get(invoice_ref, self.env["account.move"])
                if not invoice:
                    line_errors.append(
                        _("No se encontró la factura '%s' para conciliar.")
                        % invoice_ref
                    )
                elif invoice.state != "posted":
                    line_errors.append(
                        _("La factura '%s' no está confirmada (estado: %s).")
                        % (invoice_ref, invoice.state)
                    )
                elif importe - invoice.amount_residual > 0.01:
                    # account.payment.order.line._check_amount_over_original()
                    # (l10n_ar_eynes) rechaza con un error genérico en inglés
                    # si el importe supera el saldo pendiente: se valida acá
                    # antes para dar un error claro en la previsualización en
                    # vez de que reviente recién al confirmar.
                    line_errors.append(
                        _(
                            "El importe aplicado (%.2f) supera el saldo"
                            " pendiente de la factura '%s' (%.2f)."
                        )
                        % (importe, invoice_ref, invoice.amount_residual)
                    )
                else:
                    matched_partners.add(invoice.partner_id)
                    applied_total += importe

            payment_mode = None
            if line["medio_pago"]:
                payment_mode = self._lookup_payment_mode(payment_mode_by_key, line)
            if not line["medio_pago"]:
                line_errors.append(_("El recibo no informa medio de pago."))
            elif not payment_mode:
                line_errors.append(
                    _(
                        "No hay un diario mapeado para el medio de pago '%s'"
                        " + caja '%s' + cod bco '%s' + sucursal '%s'"
                        " (configurar en Contabilidad > Configuración >"
                        " Medios de pago (importación de cobros))."
                    )
                    % (
                        line["medio_pago"],
                        line["caja"],
                        line["cod_bco"],
                        line["sucursal_bco"],
                    )
                )

            try:
                importe_movimiento = self._to_float(line["importe_movimiento"])
            except (TypeError, ValueError):
                importe_movimiento = 0.0

            try:
                importe_movimiento_moneda_local = self._to_float(
                    line["importe_movimiento_moneda_local"]
                )
            except (TypeError, ValueError):
                importe_movimiento_moneda_local = 0.0

            detail_vals.append(
                (
                    0,
                    0,
                    {
                        "tipo_compr_asoc": line["tipo_compr_asoc"],
                        "letra_asoc": line["letra_asoc"],
                        "pto_venta_asoc": line["pto_venta_asoc"],
                        "numero_compr_asoc": line["numero_compr_asoc"],
                        "invoice_id": invoice.id if invoice else False,
                        "importe": importe,
                        "payment_mode_id": payment_mode.id if payment_mode else False,
                        "medio_pago": line["medio_pago"],
                        "moneda": line["moneda"],
                        "tipo_cambio": line["tipo_cambio"],
                        "caja": line["caja"],
                        "importe_movimiento": importe_movimiento,
                        "cod_bco": line["cod_bco"],
                        "sucursal_bco": line["sucursal_bco"],
                        "importe_movimiento_moneda_local": (
                            importe_movimiento_moneda_local
                        ),
                        "has_error": bool(line_errors),
                        "error_message": "; ".join(line_errors)
                        if line_errors
                        else False,
                    },
                )
            )
            errors.extend(line_errors)

        return detail_vals, errors, matched_partners, applied_total

    # ------------------------------------------------------------------
    # Paso 2 -> 3: crear los cobros que no tengan error
    # ------------------------------------------------------------------

    # Cada cuántos recibos se hace un commit() intermedio (ver
    # action_confirm): mismo criterio que
    # IvessInvoiceImportWizard._CONFIRM_CHUNK_SIZE, para que un import largo
    # no dependa de una única transacción gigante.
    # Segundos sin señal de vida a partir de los cuales una carga en proceso
    # se considera interrumpida (servidor caído o reiniciado): hay que volver
    # a empezar la carga. Cada lote informa su avance cada pocos segundos.
    _STALL_SECONDS = 120

    @api.depends("state", "last_heartbeat")
    def _compute_is_stalled(self):
        now = fields.Datetime.now()
        for wizard in self:
            wizard.is_stalled = bool(
                wizard.state == "processing"
                and wizard.last_heartbeat
                and (now - wizard.last_heartbeat).total_seconds()
                > self._STALL_SECONDS
            )

    # Cantidad de recibos a cuenta (sin facturas) que se crean y postean
    # juntos, ver _confirm_batch. 0 desactiva el modo por lotes y cada
    # recibo se procesa de a uno, como siempre.
    _CONFIRM_BATCH_SIZE = 200

    def action_confirm(self):
        """Deja la importación lista y la delega al cron: la petición no
        espera a que se creen los recibos (puede tardar varios minutos), la
        pantalla muestra una barra de progreso y la carga no se cuelga."""
        self.ensure_one()
        if self.state != "preview":
            raise UserError(_("La importación ya fue confirmada."))
        pending = self.env["ivess.payment.import.result.line"]
        for result_line in self.result_line_ids:
            if result_line.has_error:
                result_line.resultado = "error"
            elif result_line.comprobante_anulado:
                # Un recibo anulado en el sistema origen nunca llegó a
                # cobrarse: a diferencia de una factura anulada (que sí tuvo
                # CAE y debe registrarse y cancelarse para no perder
                # numeración), acá no hay nada que registrar en Odoo.
                result_line.resultado = "skipped"
            else:
                pending |= result_line
        self.write(
            {
                "state": "processing",
                "progress_total": len(pending),
                "progress_done": 0,
                "last_heartbeat": fields.Datetime.now(),
                "process_error": False,
            }
        )
        # El cron lee el wizard desde otra transacción: debe estar guardado
        # antes de dispararlo.
        self.env.cr.commit()  # pylint: disable=invalid-commit
        self._launch_processing()
        return self._reopen()

    def _launch_processing(self):
        """Arranca el procesamiento en segundo plano.

        Si el cron de Odoo atiende esta base (en producción, con una única
        base configurada), se dispara el cron. Si no (por ejemplo con una
        base restaurada para pruebas cuando el servidor se levantó con
        db_name fijo, el cron solo corre para esa base), se procesa en un
        hilo del propio servidor.
        """
        self.ensure_one()
        dbname = self.env.cr.dbname
        if dbname in cron_database_list():
            self.env.ref("ivess_invoice_import.ir_cron_payment_import")._trigger()
            return
        threading.Thread(
            target=self._process_in_thread,
            args=(dbname, self.id),
            name="ivess-payment-import-%s" % self.id,
            daemon=True,
        ).start()

    @api.model
    def _process_in_thread(self, dbname, wizard_id):
        try:
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, api.SUPERUSER_ID, {})
                env["ivess.payment.import.wizard"].browse(wizard_id)._run_pending()
        except Exception:  # pylint: disable=broad-except # noqa: BLE001
            _logger.exception(
                "Importación de cobros %s: falló el proceso en segundo plano",
                wizard_id,
            )

    @api.model
    def _cron_process_pending(self):
        """Cron: procesa las importaciones confirmadas.

        Una carga que quedó "procesando" pero sin señal de vida (el servidor
        se cayó o se reinició a mitad de camino) NO se reanuda: se marca
        como interrumpida y hay que volver a empezar la carga. Lo que ya se
        creó no se duplica: la previsualización lo detecta como "Ya existe".
        """
        for wizard in self.search([("state", "=", "processing")]):
            wizard._run_pending()

    def _run_pending(self):
        """Procesa una importación confirmada (desde el cron o desde el hilo
        en segundo plano). No reanuda una carga interrumpida."""
        self.ensure_one()
        if self.state != "processing":
            return
        if self.is_stalled:
            self.state = "interrupted"
            self._notify_user(
                _(
                    "La importación se interrumpió (el servidor dejó de"
                    " responder). Volvé a empezar la carga."
                ),
                "danger",
            )
            self.env.cr.commit()  # pylint: disable=invalid-commit
            return
        # Se procesa con el usuario que confirmó la importación (autor y
        # permisos de los recibos, igual que cuando se hacía en la misma
        # petición).
        wizard = self.with_user(self.create_uid)
        try:
            wizard._process_confirm()
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            self.env.cr.rollback()
            self.env.invalidate_all()
            wizard = self.browse(self.id)
            wizard.write({"state": "interrupted", "process_error": str(exc)})
            wizard._notify_user(
                _("La importación se interrumpió por un error: %s") % exc,
                "danger",
            )
            self.env.cr.commit()  # pylint: disable=invalid-commit

    def _process_confirm(self):
        self.ensure_one()
        # Ver IvessInvoiceImportWizard.action_confirm: tracking_disable evita
        # el overhead de chatter de mail.thread en cada create()/write(), que
        # no aporta nada en una importación histórica. mail_create_nolog y
        # mail_create_nosubscribe evitan además el mensaje de creación y los
        # seguidores de cada recibo/asiento.
        self = self.with_context(
            tracking_disable=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_auto_subscribe_no_notify=True,
        )
        done = 0
        pending_singles = 0
        batch = self.env["ivess.payment.import.result.line"]
        for result_line in self.result_line_ids.filtered(
            lambda r: r.resultado == "pending"
        ):
            if self._CONFIRM_BATCH_SIZE and self._is_batchable(result_line):
                batch |= result_line
                if len(batch) >= self._CONFIRM_BATCH_SIZE:
                    self._confirm_batch(batch)
                    done += len(batch)
                    batch = self.env["ivess.payment.import.result.line"]
                    self._report_progress(done)
                continue
            self._confirm_one(result_line)
            done += 1
            pending_singles += 1
            if pending_singles >= self._PROGRESS_EVERY:
                pending_singles = 0
                self._report_progress(done)
        if batch:
            self._confirm_batch(batch)
            done += len(batch)

        self.write(
            {
                "ok_count": len(
                    self.result_line_ids.filtered(lambda r: r.resultado == "ok")
                ),
                "error_count": len(
                    self.result_line_ids.filtered(lambda r: r.resultado == "error")
                ),
                "skipped_count": len(
                    self.result_line_ids.filtered(lambda r: r.resultado == "skipped")
                ),
                "progress_done": done,
                "last_heartbeat": fields.Datetime.now(),
                "state": "done",
            }
        )
        self._notify_user(
            _(
                "Importación finalizada: %(ok)s cobros creados, %(err)s con"
                " error y %(skipped)s anulados en origen."
            )
            % {
                "ok": self.ok_count,
                "err": self.error_count,
                "skipped": self.skipped_count,
            },
            "warning" if self.error_count else "success",
        )
        self.env.cr.commit()  # pylint: disable=invalid-commit

    # Cada cuántos recibos procesados de a uno se informa el avance.
    _PROGRESS_EVERY = 25

    def _notify_user(self, message, notification_type):
        """Avisa al usuario que confirmó la importación con una notificación
        emergente de Odoo (bus), aunque se haya ido de la pantalla del
        wizard: la importación corre en segundo plano. Es solo un aviso: si
        falla no debe afectar a la importación."""
        self.ensure_one()
        try:
            self.create_uid._bus_send(
                "simple_notification",
                {
                    "title": _("Importación de cobros"),
                    "message": message,
                    "type": notification_type,
                    "sticky": True,
                },
            )
        except Exception:  # pylint: disable=broad-except # noqa: BLE001
            _logger.exception(
                "Importación de cobros %s: no se pudo enviar la notificación",
                self.id,
            )

    def _report_progress(self, done):
        """Guarda el avance (y con él todo lo creado hasta ahora): la barra
        de progreso lo lee desde otra transacción, y si el proceso se corta
        a mitad de camino lo ya procesado queda guardado."""
        self.write({"progress_done": done, "last_heartbeat": fields.Datetime.now()})
        self.env.cr.commit()  # pylint: disable=invalid-commit

    def _confirm_one(self, result_line):
        """Crea y valida un recibo, de a uno, y registra el resultado en su
        línea de previsualización."""
        error = None
        try:
            with self.env.cr.savepoint():
                payment_order = self._create_payment_order(result_line)
            result_line.write(
                {"resultado": "ok", "odoo_payment_order_id": payment_order.id}
            )
        except psycopg2.Error as exc:
            # El savepoint ya no existe: algún módulo hizo commit() dentro de
            # la transacción antes de fallar. El error real es el que se
            # estaba manejando cuando falló el rollback.
            error = exc.__context__ or exc
            self._recover_failed_receipt(result_line)
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            error = exc
        if error is not None:
            result_line.write(
                {
                    "resultado": "error",
                    "has_error": True,
                    "error_message": _("Error al crear el cobro: %s") % error,
                }
            )

    @staticmethod
    def _is_batchable(result_line):
        """Recibo a cuenta: ninguna de sus líneas aplica a una factura."""
        details = result_line.detail_line_ids
        return bool(details) and not details.filtered("invoice_id")

    def _confirm_batch(self, result_lines):
        """Crea y postea varios recibos a cuenta juntos.

        Odoo es mucho más eficiente creando y posteando muchos registros en
        una sola llamada que de a uno (el costo fijo de cada llamada se
        reparte entre todos). Si algo falla en el lote (un recibo con un
        dato inválido, un módulo que hace commit(), etc.) se descarta el
        lote entero y se reprocesa recibo por recibo con _confirm_one, que
        es quien registra el error de cada uno.
        """
        orders = None
        try:
            with self.env.cr.savepoint():
                orders = self._create_payment_orders_batch(result_lines)
        except psycopg2.Error:
            # Un módulo hizo commit() dentro de la transacción y destruyó el
            # savepoint (ver _check_journal_period).
            self._recover_failed_receipt(result_lines)
        except Exception:  # pylint: disable=broad-except # noqa: BLE001
            pass
        if orders is None:
            for result_line in result_lines:
                self._confirm_one(result_line)
            return
        for result_line, order in zip(result_lines, orders):
            result_line.write(
                {"resultado": "ok", "odoo_payment_order_id": order.id}
            )

    def _create_payment_orders_batch(self, result_lines):
        orders = self.env["account.payment.order"].create(
            [self._prepare_order_vals(line) for line in result_lines]
        )
        self._post_receipts_batch(orders)
        return orders

    def _post_receipts_batch(self, orders):
        """Genera y postea el asiento de varios recibos a cuenta juntos.

        Es el equivalente en lote de account.payment.order.proforma_voucher /
        action_move_line_create (l10n_ar_eynes) para un recibo sin líneas de
        aplicación: mismas líneas de pago, misma línea que acredita al
        cliente, mismo número de recibo (la secuencia se consume de a uno,
        en orden), y los valores de cada asiento salen de los mismos métodos
        de l10n_ar_eynes (account_move_get, create_move_lines y
        writeoff_move_line_get). Todo lo que no sea el caso simple lanza
        UserError y _confirm_batch lo procesa por el camino de siempre.
        """
        for order in orders:
            self._check_batch_supported(order)
        ctx = {"check_move_validity": False, "skip_invoice_sync": True}
        for order in orders:
            order.number = order.get_next_sequence(consume=True)
        moves = (
            self.env["account.move"]
            .with_context(**ctx)
            .create([order.account_move_get() for order in orders])
        )
        line_vals = []
        for order, move in zip(orders, moves):
            lines = order.create_move_lines(move.id)
            line_total = sum(line["debit"] - line["credit"] for line in lines)
            writeoff = order.writeoff_move_line_get(line_total, move.id, move.name)
            line_vals += lines + ([writeoff] if writeoff else [])
        self.env["account.move.line"].with_context(**ctx).create(line_vals)
        moves.action_post()
        for order, move in zip(orders, moves):
            order.write(
                {"move_id": move.id, "state": "posted", "posted_before": True}
            )

    @staticmethod
    def _check_batch_supported(order):
        """El modo por lotes solo cubre el recibo a cuenta simple (sin
        retenciones, cheques, conceptos ni líneas de aplicación) y repite las
        validaciones de proforma_voucher que le aplican."""
        if (
            order.line_ids
            or order.concept_line_ids
            or order.retention_ids
            or order.third_party_check_receipt_ids
            or order.third_party_check_ids
            or order.issued_check_ids
        ):
            raise UserError(_("El recibo no es un cobro a cuenta simple."))
        if round(order.writeoff_amount, 2) < 0.0 or not order.amount:
            raise UserError(_("Importe del recibo inválido."))
        if not order.payment_rate:
            raise UserError(_("Tipo de cambio del recibo inválido."))

    def _prepare_order_vals(self, result_line):
        journal = result_line.journal_id
        company = journal.company_id
        # Misma moneda que calcula account.payment.order
        # (_compute_default_journal_currency): la del diario o, si no tiene,
        # la de la compañía.
        currency = journal.currency_id or company.currency_id
        # Un único create() con las líneas incluidas: evita los dos write()
        # posteriores (income_line_ids / payment_mode_line_ids), cada uno
        # con su propio recálculo de campos dependientes.
        return {
            "partner_id": result_line.partner_id.id,
            "journal_id": journal.id,
            "type": "receipt",
            "company_id": company.id,
            "date": result_line.fecha,
            "reference": result_line.comprobante_ref,
            "name": result_line.comprobante_ref,
            "disable_retentions": True,
            "income_line_ids": [
                (0, 0, vals)
                for vals in self._prepare_income_line_vals(
                    currency, company, result_line
                )
            ],
            "payment_mode_line_ids": [
                (0, 0, vals)
                for vals in self._prepare_payment_mode_line_vals(result_line)
            ],
        }

    def _create_payment_order(self, result_line):
        order = self.env["account.payment.order"].create(
            self._prepare_order_vals(result_line)
        )
        result = order.proforma_voucher()
        # proforma_voucher no lanza ante un error al generar el asiento:
        # lo captura, deja el recibo en borrador y devuelve un popup.
        if order.state != "posted":
            message = (
                result.get("context", {}).get("message")
                if isinstance(result, dict)
                else None
            )
            raise UserError(
                message or _("No se pudo validar el recibo de cobranza.")
            )
        return order

    @staticmethod
    def _prepare_payment_mode_line_vals(result_line):
        """Agrupa las líneas de detalle por diario de medio de pago resuelto
        (payment_mode_id, ver _resolve_detail_lines) y arma una
        payment_mode_line por cada diario distinto, con el importe sumado
        de las facturas aplicadas con ese medio de pago: un mismo recibo
        puede combinar más de un medio de pago (ej. parte efectivo, parte
        cheque)."""
        amounts_by_journal = {}
        order_by_journal = []
        for detail in result_line.detail_line_ids:
            journal = detail.payment_mode_id
            if journal.id not in amounts_by_journal:
                amounts_by_journal[journal.id] = 0.0
                order_by_journal.append(journal)
            amounts_by_journal[journal.id] += detail.importe

        return [
            {
                "payment_mode_id": journal.id,
                "amount": amounts_by_journal[journal.id],
                "name": result_line.comprobante_ref,
                "date": result_line.fecha,
            }
            for journal in order_by_journal
        ]

    @staticmethod
    def _prepare_income_line_vals(currency, company, result_line):
        income_vals = []
        for detail in result_line.detail_line_ids:
            invoice = detail.invoice_id
            if not invoice:
                # Línea de recibo a cuenta (sin factura): solo aporta su
                # medio de pago, no hay nada que aplicar.
                continue
            move_line = invoice.line_ids.filtered(
                lambda aml: aml.account_id.account_type == "asset_receivable"
                and not aml.reconciled
            )[:1]
            if not move_line:
                raise UserError(
                    _(
                        "La factura '%s' no tiene un apunte a cobrar"
                        " pendiente de conciliar."
                    )
                    % invoice.display_name
                )
            income_vals.append(
                {
                    "invoice_id": invoice.id,
                    "move_line_id": move_line.id,
                    "account_id": move_line.account_id.id,
                    "amount": detail.importe,
                    "type": "income",
                    "currency_id": currency.id,
                    "original_currency_id": company.currency_id.id,
                }
            )
        return income_vals
