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

# Columnas opcionales del cheque (formato nuevo): van entre "importe del
# movimiento" y "cod bco", por lo que desplazan las columnas siguientes.
CHECK_HEADERS = [
    "numero de cheque",
    "tipo de cheque",
    "formato",
    "fecha de recepcion",
    "fecha de emision",
    "fecha de vencimiento",
]
CHECK_FIRST_COLUMN = 18

# Columnas que identifican la cabecera del recibo agrupado (mismo criterio
# que GROUP_KEY_FIELDS de invoice_import_wizard.py).
# Posición (base 0) de la columna "retencion 1"; luego alternan código/monto.
RETENTION_FIRST_COLUMN = 21
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
    "cheque_cols",
    "nro_cheque",
    "tipo_cheque",
    "formato_cheque",
    "fecha_recepcion",
    "fecha_emision_cheque",
    "fecha_vto_cheque",
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
            group["retenciones"] = row.get("retenciones") or []
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
    # Código de "medio de pago" que identifica cheque de terceros.
    _CHECK_MEDIO_PAGO = "2"
    _CHECK_TYPES = {"COMUN": "common", "DIFERIDO": "deferred"}
    _CHECK_FORMATS = {"FISICO": "physical", "ECHEQ": "echeq"}

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
        # Formato nuevo: trae 6 columnas de cheque antes de "cod bco".
        with_checks = headers[
            CHECK_FIRST_COLUMN : CHECK_FIRST_COLUMN + len(CHECK_HEADERS)
        ] == CHECK_HEADERS
        expected_headers = list(EXPECTED_HEADERS)
        if with_checks:
            expected_headers[CHECK_FIRST_COLUMN:CHECK_FIRST_COLUMN] = CHECK_HEADERS
        mismatches = [
            _("columna %d: se esperaba '%s', se encontró '%s'")
            % (i + 1, expected, headers[i] if i < len(headers) else "")
            for i, expected in enumerate(expected_headers)
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
            rows.append(self._row_to_dict(raw_row, row_number, with_checks))
        return rows

    def _row_to_dict(self, raw_row, row_number, with_checks=False):
        shift = len(CHECK_HEADERS) if with_checks else 0

        def cell(index):
            return raw_row[index] if index < len(raw_row) else None

        def check_cell(offset):
            return cell(CHECK_FIRST_COLUMN + offset) if with_checks else None

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
            "cod_bco": self._to_str(cell(18 + shift)),
            "sucursal_bco": self._to_str(cell(19 + shift)),
            "importe_movimiento_moneda_local": cell(20 + shift),
            "cheque_cols": with_checks,
            "nro_cheque": self._to_str(check_cell(0)),
            "tipo_cheque": self._to_str(check_cell(1)).upper(),
            "formato_cheque": self._to_str(check_cell(2)).upper(),
            "fecha_recepcion": check_cell(3),
            "fecha_emision_cheque": check_cell(4),
            "fecha_vto_cheque": check_cell(5),
            "retenciones": self._read_retentions(cell, RETENTION_FIRST_COLUMN + shift),
        }

    def _read_retentions(self, cell, first_column=RETENTION_FIRST_COLUMN):
        """Pares (código, monto) de las columnas opcionales "retencion N" /
        "monto retencion N" (N = 1..5, a partir de la columna 22). Un recibo
        puede traer hasta 5 retenciones distintas."""
        retentions = []
        for index in range(first_column, first_column + 10, 2):
            code = self._to_str(cell(index))
            amount = cell(index + 1)
            if code or amount not in (None, ""):
                retentions.append((code, amount))
        return retentions

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

        receipt_journal_by_tipo = self._find_receipt_journals_by_tipo(groups)
        check_ctx = self._build_check_context(groups)

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
                group["lines"], invoice_by_ref, payment_mode_by_key, check_ctx
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

        retention_tax_by_code = {
            mapping.code: mapping.tax_id
            for mapping in self.env["ivess.payment.import.retention.code"].search(
                [("company_id", "=", self.env.company.id)]
            )
        }

        return {
            "retention_tax_by_code": retention_tax_by_code,
            "receipt_journal_by_tipo": receipt_journal_by_tipo,
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

        journal, journal_candidates = cache["receipt_journal_by_tipo"][
            group["tipo_comprobante"]
        ]
        if not journal:
            if journal_candidates:
                errors.append(
                    _(
                        "El tipo de comprobante '%(tipo)s' coincide con"
                        " %(count)s diarios de tipo 'Recibo de Cobranza'"
                        " (código POS); debe coincidir con uno solo."
                    )
                    % {"tipo": group["tipo_comprobante"], "count": journal_candidates}
                )
            else:
                errors.append(
                    _(
                        "No se encontró un diario de tipo 'Recibo de Cobranza'"
                        " (account.journal type='receipt') con código POS"
                        " '%s'."
                    )
                    % group["tipo_comprobante"]
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

        retention_vals, retention_errors = self._resolve_retentions(
            group, cache, importe_total
        )
        errors.extend(retention_errors)

        # En un recibo a cuenta el importe del movimiento es lo cobrado por
        # el medio de pago, sin las retenciones: el total del recibo es
        # cobrado + retenciones. Si el recibo aplica a facturas, el importe
        # aplicado ya es el bruto (incluye las retenciones).
        retention_total = sum(vals[2]["importe"] for vals in retention_vals)
        on_account = not any(
            not self._is_on_account_line(line) for line in group["lines"]
        )
        expected_total = applied_total + (retention_total if on_account else 0.0)
        if not errors and abs(expected_total - importe_total) > 0.01:
            errors.append(
                _(
                    "La suma de los importes del recibo (%.2f) no coincide con"
                    " el importe total del recibo (%.2f)."
                )
                % (expected_total, importe_total)
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
            "retention_line_ids": retention_vals,
        }

    def _resolve_retentions(self, group, cache, importe_total):
        """Resuelve las retenciones del recibo contra el mapeo configurable
        ivess.payment.import.retention.code.

        :return: tupla (comandos create para retention_line_ids, errores).
        """
        errors = []
        vals = []
        total = 0.0
        for code, raw_amount in group.get("retenciones") or []:
            if not code:
                errors.append(
                    _("Hay un monto de retención (%s) sin código de retención.")
                    % raw_amount
                )
                continue
            try:
                amount = self._to_float(raw_amount) if raw_amount not in (None, "") else 0.0
            except (TypeError, ValueError):
                errors.append(
                    _("Monto inválido para la retención '%(code)s': '%(amount)s'.")
                    % {"code": code, "amount": raw_amount}
                )
                continue
            tax = cache["retention_tax_by_code"].get(code)
            line_error = False
            if not tax:
                line_error = _(
                    "No hay una retención configurada para el código '%s'"
                    " (Contabilidad > Configuración > Retenciones"
                    " (importación de cobros))."
                ) % code
                errors.append(line_error)
            elif not amount:
                line_error = _("La retención '%s' tiene monto cero.") % code
                errors.append(line_error)
            total += amount
            vals.append(
                (
                    0,
                    0,
                    {
                        "codigo": code,
                        "tax_id": tax.id if tax else False,
                        "importe": amount,
                        "has_error": bool(line_error),
                        "error_message": line_error,
                    },
                )
            )
        if total and total - importe_total > 0.01:
            errors.append(
                _(
                    "La suma de las retenciones (%.2f) supera el importe total"
                    " del recibo (%.2f)."
                )
                % (total, importe_total)
            )
        return vals, errors

    def _find_receipt_journals_by_tipo(self, groups):
        """Resuelve el diario de Recibo de Cobranza (account.journal con
        type='receipt') de la compañía activa para cada tipo de comprobante
        distinto del archivo (primera columna: RMP, BJU, RTT, etc.).

        El diario se identifica por su código POS (account.journal.code),
        que debe ser igual al tipo de comprobante (sin distinguir
        mayúsculas). El punto de venta del recibo no interviene.

        :return: dict tipo_comprobante -> (diario o None, cantidad de
            diarios candidatos).
        """
        journals = self.env["account.journal"].search(
            [
                ("type", "=", "receipt"),
                ("company_id", "=", self.env.company.id),
            ]
        )
        result = {}
        for tipo in {g["tipo_comprobante"] for g in groups if not g.get("error")}:
            matches = journals.filtered(
                lambda j, tipo=tipo: (j.code or "").strip().upper() == tipo
            )
            result[tipo] = (matches[0] if len(matches) == 1 else None, len(matches))
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

    def _is_check_line(self, line):
        """Línea cobrada con cheque de terceros: medio de pago '2' en un
        archivo con las columnas de cheque. Sin esas columnas (formato
        anterior) el medio '2' sigue resolviéndose por el mapeo a diario."""
        return bool(
            line.get("cheque_cols") and line["medio_pago"] == self._CHECK_MEDIO_PAGO
        )

    def _build_check_context(self, groups):
        """Diario de cheques de terceros y bancos (por código BCRA, que es el
        BIC del banco como en el mapeo de medios de pago) para resolver los
        cheques del archivo en lote."""
        uses_checks = any(
            self._is_check_line(line)
            for group in groups
            if not group.get("error")
            for line in group["lines"]
        )
        if not uses_checks:
            return {"journal": None, "bank_by_code": {}, "existing": set(), "seen": {}}
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "third_party_checks"),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        bank_by_code = {}
        for bank in self.env["res.bank"].search([("bic", "!=", False)]):
            bank_by_code.setdefault(self._norm_bank_code(bank.bic), bank)
        # Cheques de terceros ya registrados con los números del archivo
        # (número, banco): el mismo cheque no puede entrar dos veces.
        numbers = {
            line["nro_cheque"].zfill(8)
            for group in groups
            if not group.get("error")
            for line in group["lines"]
            if self._is_check_line(line) and line["nro_cheque"].isdigit()
        }
        existing = {
            (check.number, check.bank_id.id): check
            for check in self.env["account.check"].search(
                [
                    ("internal_type", "=", "third_party"),
                    ("number", "in", list(numbers)),
                    ("third_party_check_state", "!=", "cancelled"),
                    ("company_id", "=", self.env.company.id),
                ]
            )
        }
        return {
            "journal": journal,
            "bank_by_code": bank_by_code,
            "existing": existing,
            # (número, banco) -> recibo del archivo que lo trae primero.
            "seen": {},
        }

    def _resolve_check_line(self, line, check_ctx, owner=None):
        """Valida y resuelve los datos del cheque de una línea. Devuelve
        (vals para la línea de detalle, errores)."""
        errors = []
        vals = {"is_check": True}

        number = line["nro_cheque"]
        if not number:
            errors.append(_("El cheque no informa número."))
        elif not number.isdigit() or len(number) > 8:
            errors.append(
                _("Número de cheque inválido '%s' (hasta 8 dígitos).") % number
            )
        vals["nro_cheque"] = number.zfill(8) if number.isdigit() else number

        check_type = self._CHECK_TYPES.get(line["tipo_cheque"])
        if not check_type:
            errors.append(
                _("Tipo de cheque '%s' no soportado (COMUN o DIFERIDO).")
                % line["tipo_cheque"]
            )
        vals["check_type"] = check_type

        check_format = self._CHECK_FORMATS.get(line["formato_cheque"])
        if not check_format:
            errors.append(
                _("Formato de cheque '%s' no soportado (FISICO o ECHEQ).")
                % line["formato_cheque"]
            )
        vals["check_format"] = check_format

        for field, source, label in (
            ("reception_date", "fecha_recepcion", _("fecha de recepción")),
            ("issue_date", "fecha_emision_cheque", _("fecha de emisión")),
            ("payment_date", "fecha_vto_cheque", _("fecha de vencimiento")),
        ):
            raw = line[source]
            vals[field] = False
            if raw in (None, ""):
                # El vencimiento solo es obligatorio para el cheque diferido.
                if field != "payment_date" or check_type == "deferred":
                    errors.append(_("El cheque no informa %s.") % label)
                continue
            try:
                vals[field] = self._to_date(raw)
            except ValueError:
                errors.append(_("El cheque trae una %s inválida: '%s'.") % (label, raw))

        bank = check_ctx["bank_by_code"].get(self._norm_bank_code(line["cod_bco"]))
        if not line["cod_bco"]:
            errors.append(_("El cheque no informa código de banco."))
        elif not bank:
            errors.append(
                _("No se encontró un banco con código (BIC) '%s'.") % line["cod_bco"]
            )
        vals["bank_id"] = bank.id if bank else False

        if bank and vals["nro_cheque"].isdigit():
            key = (vals["nro_cheque"], bank.id)
            registered = check_ctx["existing"].get(key)
            if registered:
                errors.append(
                    _(
                        "El cheque %(number)s del banco %(bank)s ya está registrado"
                        " (cheque de terceros #%(id)s, estado: %(state)s)."
                    )
                    % {
                        "number": vals["nro_cheque"],
                        "bank": bank.name,
                        "id": registered.id,
                        "state": registered.third_party_check_state,
                    }
                )
            elif check_ctx["seen"].setdefault(key, owner) != owner:
                errors.append(
                    _(
                        "El cheque %(number)s del banco %(bank)s aparece en más"
                        " de un recibo del archivo."
                    )
                    % {"number": vals["nro_cheque"], "bank": bank.name}
                )

        if not check_ctx["journal"]:
            errors.append(
                _(
                    "No hay un diario de tipo 'Cheques de terceros' en la"
                    " compañía."
                )
            )
        return vals, errors

    def _resolve_detail_lines(
        self, lines, invoice_by_ref, payment_mode_by_key, check_ctx=None
    ):
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
            check_vals = {}
            is_check = check_ctx is not None and self._is_check_line(line)
            if is_check:
                # El cheque no va por un diario mapeado: se carga como cheque
                # de terceros del recibo.
                check_vals, check_errors = self._resolve_check_line(
                    line, check_ctx, owner=id(lines)
                )
                line_errors.extend(check_errors)
            elif line["medio_pago"]:
                payment_mode = self._lookup_payment_mode(payment_mode_by_key, line)
            if not line["medio_pago"]:
                line_errors.append(_("El recibo no informa medio de pago."))
            elif not is_check and not payment_mode:
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
                        **check_vals,
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
        """Recibo a cuenta (ninguna de sus líneas aplica a una factura) y sin
        retenciones ni cheques: las retenciones y los cheques van por
        proforma_voucher, uno por uno."""
        details = result_line.detail_line_ids
        return (
            bool(details)
            and not details.filtered("invoice_id")
            and not details.filtered("is_check")
            and not result_line.retention_line_ids
        )

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
        cliente, mismo número de recibo (el del Excel, no el de la secuencia del
        diario), y los valores de cada asiento salen de los mismos métodos
        de l10n_ar_eynes (account_move_get, create_move_lines y
        writeoff_move_line_get). Todo lo que no sea el caso simple lanza
        UserError y _confirm_batch lo procesa por el camino de siempre.
        """
        for order in orders:
            self._check_batch_supported(order)
        ctx = {"check_move_validity": False, "skip_invoice_sync": True}
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
            # Número del recibo = punto de venta + número del Excel, no la
            # secuencia del diario. posted_before=True evita que
            # proforma_voucher lo pise con get_next_sequence().
            "number": self._receipt_number(result_line),
            "posted_before": True,
            "disable_retentions": True,
            "retention_ids": [
                (0, 0, vals)
                for vals in self._prepare_retention_line_vals(result_line)
            ],
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
            "third_party_check_receipt_ids": [
                (0, 0, vals) for vals in self._prepare_check_vals(result_line)
            ],
        }

    @staticmethod
    def _prepare_retention_line_vals(result_line):
        """Una account.payment.order.retention.line por cada retención del
        Excel (monto tal cual, la base es el importe total del recibo)."""
        return [
            {
                "retention_id": retention.tax_id.id,
                "name": retention.tax_id.name,
                "account_id": retention.tax_id.get_retention_account().id,
                "amount": retention.importe,
                "base": result_line.importe_total,
                "base_amount": result_line.importe_total,
                "date": result_line.fecha,
            }
            for retention in result_line.retention_line_ids
        ]

    @staticmethod
    def _receipt_number(result_line):
        """Número del recibo con el formato PPPP-NNNNNNNN armado con las
        columnas "pto de vta" y "num de comprobante" del Excel."""
        return "%s-%s" % (
            (result_line.pto_vta or "").zfill(4),
            (result_line.numero_comprobante or "").zfill(8),
        )

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
    def _net_amounts(result_line):
        """Importe por diario de medio de pago (sin cheques) y por cheque
        (clave: (número, banco)), ya netos de retenciones, en el orden del
        archivo. Un mismo cheque repartido en varias facturas es uno solo."""
        mode_amounts = {}
        check_amounts = {}
        check_detail = {}
        for detail in result_line.detail_line_ids:
            if detail.is_check:
                key = (detail.nro_cheque, detail.bank_id.id)
                check_amounts[key] = check_amounts.get(key, 0.0) + detail.importe
                check_detail.setdefault(key, detail)
            else:
                journal = detail.payment_mode_id
                mode_amounts[journal] = mode_amounts.get(journal, 0.0) + detail.importe

        # Odoo calcula amount = medios de pago + cheques + retenciones. Si el
        # recibo aplica a facturas, el importe aplicado es el bruto y las
        # retenciones se descuentan de los medios de pago (empezando por el
        # primero, después los cheques) para que cuadre.
        # Solo si el recibo aplica a facturas: en un recibo a cuenta el
        # importe del movimiento ya es el neto cobrado.
        to_deduct = 0.0
        if result_line.detail_line_ids.filtered("invoice_id"):
            to_deduct = sum(result_line.retention_line_ids.mapped("importe"))
        for amounts in (mode_amounts, check_amounts):
            for key in amounts:
                deduction = min(to_deduct, amounts[key])
                amounts[key] -= deduction
                to_deduct -= deduction
        return mode_amounts, check_amounts, check_detail

    @staticmethod
    def _prepare_payment_mode_line_vals(result_line):
        """Una payment_mode_line por cada diario de medio de pago distinto
        resuelto (payment_mode_id, ver _resolve_detail_lines), con el
        importe sumado de las líneas con ese medio de pago: un mismo recibo
        puede combinar más de un medio de pago (ej. parte efectivo, parte
        transferencia). Los cheques no van acá (ver _prepare_check_vals)."""
        mode_amounts, _checks, _detail = IvessPaymentImportWizard._net_amounts(
            result_line
        )
        return [
            {
                "payment_mode_id": journal.id,
                "amount": amount,
                "name": result_line.comprobante_ref,
                "date": result_line.fecha,
            }
            for journal, amount in mode_amounts.items()
        ]

    def _prepare_check_vals(self, result_line):
        """Un cheque de terceros (account.check) por cada cheque del
        recibo; al postear el recibo pasa a 'En cartera'."""
        _modes, check_amounts, check_detail = self._net_amounts(result_line)
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "third_party_checks"),
                ("company_id", "=", result_line.journal_id.company_id.id),
            ],
            limit=1,
        )
        vals_list = []
        for key, amount in check_amounts.items():
            detail = check_detail[key]
            vals_list.append(
                {
                    "internal_type": "third_party",
                    "journal_id": journal.id,
                    "number": detail.nro_cheque,
                    "bank_id": detail.bank_id.id,
                    "type": detail.check_type,
                    "checkbook_format": detail.check_format,
                    "amount": amount,
                    "reception_date": detail.reception_date,
                    "issue_date": detail.issue_date,
                    "payment_date": detail.payment_date,
                }
            )
        return vals_list

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
