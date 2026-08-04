import base64
import io
from datetime import datetime

from odoo import _, fields, models
from odoo.exceptions import UserError

from .invoice_import_wizard import IvessInvoiceImportWizard

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

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
                    "error": _(
                        "Fila %s: faltan datos de comprobante (%s)."
                    )
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

    file = fields.Binary(string="Archivo (.xlsx)", required=True)
    filename = fields.Char(string="Nombre de archivo")
    payment_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de cobros",
        domain=[("type", "in", ("cash", "bank"))],
        help="Diario a usar para los cobros de cliente importados. Las"
        " columnas 'medio de pago' y 'caja' del archivo se muestran solo a"
        " título informativo: no determinan el diario en esta versión.",
    )
    state = fields.Selection(
        [
            ("upload", "Subir archivo"),
            ("preview", "Previsualización"),
            ("done", "Resultado"),
        ],
        default="upload",
    )
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
                _("Falta la librería 'openpyxl' en el servidor para leer archivos .xlsx.")
            )
        if not self.payment_journal_id:
            raise UserError(_("Seleccioná el diario de cobros antes de previsualizar."))

        rows = self._read_excel_rows(base64.b64decode(self.file))
        groups = group_payment_rows(rows)

        self.result_line_ids.unlink()
        for group in groups:
            self._create_preview_line(group)

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

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

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
        return float(str(value).strip())

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
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            raise UserError(_("No se pudo leer el archivo como Excel: %s") % exc) from exc

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
    # Resolución de cada grupo contra Odoo (cliente vía la factura que
    # cancela cada línea de aplicación) y creación de las líneas de
    # previsualización.
    # ------------------------------------------------------------------

    def _create_preview_line(self, group):
        if group.get("error"):
            self.env["ivess.payment.import.result.line"].create(
                {
                    "wizard_id": self.id,
                    "tipo_comprobante": group["tipo_comprobante"],
                    "letra": group["letra"],
                    "pto_vta": group["pto_vta"],
                    "numero_comprobante": group["num_compr"],
                    "has_error": True,
                    "error_message": group["error"],
                }
            )
            return

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

        detail_vals, detail_errors, matched_partners, applied_total = self._resolve_detail_lines(
            group["lines"]
        )
        errors.extend(detail_errors)

        partner = False
        if not matched_partners:
            errors.append(
                _(
                    "No se pudo determinar el cliente: ninguna factura"
                    " aplicada pudo resolverse."
                )
            )
        elif len(matched_partners) > 1:
            errors.append(
                _(
                    "El recibo aplica a facturas de más de un cliente"
                    " distinto (%s); no se puede determinar un único cliente."
                )
                % ", ".join(sorted(p.display_name for p in matched_partners))
            )
        else:
            partner = list(matched_partners)[0]

        if not errors and abs(applied_total - importe_total) > 0.01:
            errors.append(
                _(
                    "La suma de los importes aplicados a facturas (%.2f) no"
                    " coincide con el importe total del recibo (%.2f)."
                )
                % (applied_total, importe_total)
            )

        if partner and not group["comprobante_anulado"]:
            existing = self.env["account.payment"].search(
                [
                    ("payment_reference", "=", comprobante_ref),
                    ("partner_id", "=", partner.id),
                ],
                limit=1,
            )
            if existing:
                errors.append(
                    _("Ya existe un cobro importado con esta clave (account.payment #%s).")
                    % existing.id
                )

        self.env["ivess.payment.import.result.line"].create(
            {
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
                "has_error": bool(errors),
                "error_message": "\n".join(errors) if errors else False,
                "detail_line_ids": detail_vals,
            }
        )

    def _resolve_detail_lines(self, lines):
        detail_vals = []
        errors = []
        matched_partners = set()
        applied_total = 0.0

        if not lines:
            errors.append(_("El recibo no tiene líneas de aplicación a facturas."))
            return detail_vals, errors, matched_partners, applied_total

        for line in lines:
            line_errors = []

            try:
                importe = self._to_float(line["importe"])
            except (TypeError, ValueError):
                importe = 0.0
                line_errors.append(_("Importe inválido: '%s'.") % line["importe"])

            invoice = self.env["account.move"]
            if line["tipo_compr_asoc"] != "FC":
                line_errors.append(
                    _("tipo de comprobante asociado '%s' no soportado (solo 'FC').")
                    % line["tipo_compr_asoc"]
                )
            else:
                invoice_ref = IvessInvoiceImportWizard._comprobante_ref(
                    line["letra_asoc"], line["pto_venta_asoc"], line["numero_compr_asoc"]
                )
                invoice = self.env["account.move"].search(
                    [("move_type", "=", "out_invoice"), ("ref", "=", invoice_ref)],
                    limit=1,
                )
                if not invoice:
                    line_errors.append(
                        _("No se encontró la factura '%s' para conciliar.") % invoice_ref
                    )
                elif invoice.state != "posted":
                    line_errors.append(
                        _("La factura '%s' no está confirmada (estado: %s).")
                        % (invoice_ref, invoice.state)
                    )
                else:
                    matched_partners.add(invoice.partner_id)
                    applied_total += importe

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
                        "medio_pago": line["medio_pago"],
                        "moneda": line["moneda"],
                        "tipo_cambio": line["tipo_cambio"],
                        "caja": line["caja"],
                        "importe_movimiento": importe_movimiento,
                        "cod_bco": line["cod_bco"],
                        "sucursal_bco": line["sucursal_bco"],
                        "importe_movimiento_moneda_local": importe_movimiento_moneda_local,
                        "has_error": bool(line_errors),
                        "error_message": "; ".join(line_errors) if line_errors else False,
                    },
                )
            )
            errors.extend(line_errors)

        return detail_vals, errors, matched_partners, applied_total

    # ------------------------------------------------------------------
    # Paso 2 -> 3: crear los cobros que no tengan error
    # ------------------------------------------------------------------

    def action_confirm(self):
        self.ensure_one()
        for result_line in self.result_line_ids:
            if result_line.has_error:
                result_line.resultado = "error"
                continue
            if result_line.comprobante_anulado:
                # Un recibo anulado en el sistema origen nunca llegó a
                # cobrarse: a diferencia de una factura anulada (que sí tuvo
                # CAE y debe registrarse y cancelarse para no perder
                # numeración), acá no hay nada que registrar en Odoo.
                result_line.resultado = "skipped"
                continue
            try:
                with self.env.cr.savepoint():
                    payment = self._create_payment(result_line)
                result_line.write({"resultado": "ok", "odoo_payment_id": payment.id})
            except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
                result_line.write(
                    {
                        "resultado": "error",
                        "has_error": True,
                        "error_message": _("Error al crear el cobro: %s") % exc,
                    }
                )

        self.ok_count = len(self.result_line_ids.filtered(lambda r: r.resultado == "ok"))
        self.error_count = len(self.result_line_ids.filtered(lambda r: r.resultado == "error"))
        self.skipped_count = len(
            self.result_line_ids.filtered(lambda r: r.resultado == "skipped")
        )
        self.state = "done"
        return self._reopen()

    def _create_payment(self, result_line):
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": result_line.partner_id.id,
                "amount": result_line.importe_total,
                "journal_id": self.payment_journal_id.id,
                "date": result_line.fecha,
                "memo": result_line.comprobante_ref,
                "payment_reference": result_line.comprobante_ref,
            }
        )
        payment.action_post()
        if not payment.move_id:
            # Odoo no generó el asiento del pago: pasa en silencio (sin
            # excepción) cuando el método de pago usado no tiene configurada
            # la cuenta puente (account.payment.method.line.payment_account_id).
            # Sin asiento no hay nada que conciliar, así que se corta acá en
            # vez de dejar el cobro marcado como "ok" sin haber conciliado
            # nada.
            raise UserError(
                _(
                    "Odoo no generó el asiento contable del pago: el método"
                    " de pago del diario '%s' no tiene configurada la cuenta"
                    " puente (payment_account_id). Hay que corregir esa"
                    " configuración contable antes de poder importar cobros."
                )
                % self.payment_journal_id.display_name
            )
        self._reconcile_payment(payment, result_line.detail_line_ids.mapped("invoice_id"))
        return payment

    @staticmethod
    def _reconcile_payment(payment, invoices):
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        )
        invoice_lines = invoices.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        )
        all_lines = payment_lines + invoice_lines
        for account in all_lines.account_id:
            all_lines.filtered(lambda l, account=account: l.account_id == account).reconcile()
