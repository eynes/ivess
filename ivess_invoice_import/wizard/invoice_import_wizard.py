import base64
import csv
import io
from datetime import datetime

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

EXPECTED_HEADERS = [
    "tipo de comprobante",
    "letra",
    "pto vta",
    "numero comprob",
    "fecha",
    "cod cliente",
    "razon social",
    "documento",
    "fecha vto",
    "importe total",
    "comprobante anulado",
    "cae",
    "vto cae",
    "tipo de item",
    "cod art",
    "cantidad",
    "precio unitario",
    "tasa de iva",
    "tasa de iva no inscripto",
    "importe iva inscripto",
    "importe iva no inscripto",
    "importe total neto del item",
    "importe del renglon",
    "cod impuesto interno",
    "monto imp interno",
    "cod imp especiales",
    "monto imp especiales",
    "base imp especiales",
    "cod imp especiales1",
    "monto imp especiales1",
    "base imp especiales1",
    "cod imp especiales2",
    "monto imp especiales2",
    "base imp especiales2",
]

# Columnas de impuesto especial/interno del Excel: cada tupla es (columna de
# código, columna de monto, columna de base imponible). "cod impuesto
# interno" es la única sin columna de base propia: el impuesto interno no
# tiene base imponible, así que su base se informa siempre en 0. El resto
# ("cod imp especiales", "...especiales1", "...especiales2") sí trae su
# propia base imponible en el Excel. Todas matchean igual: por código
# Bejerman (ver AccountTax.bejerman_code) o, si no matchea, por el mapeo
# manual de ivess.invoice.import.tax.code.
SPECIAL_TAX_COLUMNS = [
    ("cod impuesto interno", "monto imp interno", None),
    ("cod imp especiales", "monto imp especiales", "base imp especiales"),
    ("cod imp especiales1", "monto imp especiales1", "base imp especiales1"),
    ("cod imp especiales2", "monto imp especiales2", "base imp especiales2"),
]

# Mapeo tipo de comprobante (columna del Excel) -> res.voucher.type.doc_type,
# para resolver el comprobante Odoo (FC=Factura, ND=Nota de Débito, NC=Nota
# de Crédito) y derivar el move_type/is_debit_note correspondiente.
TIPO_COMPROBANTE_DOC_TYPES = {
    "FC": "b",
    "ND": "dn",
    "NC": "cn",
}

# Columnas que identifican la cabecera de la factura agrupada. Se toman del
# PRIMER renglón visto de cada grupo (decisión confirmada: si difieren entre
# renglones del mismo comprobante -como puede pasar con fecha vto/importe
# total en archivos reales- se ignora la diferencia y se usa el primero).
GROUP_KEY_FIELDS = ("tipo_comprobante", "letra", "pto_vta", "numero_comprob")
HEADER_ONLY_FIELDS = (
    "fecha",
    "cod_cliente",
    "razon_social",
    "documento",
    "fecha_vto",
    "importe_total",
    "comprobante_anulado",
    "cae",
    "vto_cae",
)
DETAIL_FIELDS = (
    "tipo_item",
    "cod_art",
    "cantidad",
    "precio_unitario",
    "tasa_iva",
    "tasa_iva_no_inscripto",
    "importe_iva_inscripto",
    "importe_iva_no_inscripto",
    "importe_total_neto_item",
    "importe_del_renglon",
    "special_taxes",
)


def group_invoice_rows(rows):
    """Agrupa renglones desnormalizados de factura (una fila por ítem) en
    facturas (cabecera + líneas de detalle), por (tipo_comprobante, letra,
    pto_vta, numero_comprob).

    :param rows: lista de dicts, cada uno con al menos las claves de
        GROUP_KEY_FIELDS + HEADER_ONLY_FIELDS + DETAIL_FIELDS (además puede
        traer "_row_number" para trazabilidad de errores).
    :return: lista de dicts, cada uno con las claves de GROUP_KEY_FIELDS +
        HEADER_ONLY_FIELDS + "lines" (lista de dicts con DETAIL_FIELDS) +
        "row_numbers" (números de fila origen) + "error" (str u None, para
        renglones que no se pudieron agrupar por faltarles la clave).
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
                    "numero_comprob": row.get("numero_comprob") or "",
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


class IvessInvoiceImportWizard(models.TransientModel):
    _name = "ivess.invoice.import.wizard"
    _description = "Importador de facturas de clientes desde archivo Excel"

    file = fields.Binary(string="Archivo (.xlsx)", required=True)
    filename = fields.Char(string="Nombre de archivo")
    state = fields.Selection(
        [
            ("upload", "Subir archivo"),
            ("preview", "Previsualización"),
            ("done", "Resultado"),
        ],
        default="upload",
    )
    result_line_ids = fields.One2many(
        "ivess.invoice.import.result.line",
        "wizard_id",
        string="Facturas",
    )
    # Dos One2many al mismo modelo/inverse pero con domain propio: a
    # diferencia del atributo "domain" de la vista (que en un widget
    # one2many embebido solo se usa para el diálogo de "agregar
    # existente", NO filtra las filas ya cargadas), un domain a nivel de
    # campo sí restringe qué filas trae el ORM al leerlo. Se usan para que
    # los botones "Ver OK"/"Ver errores" muestren cada uno una lista
    # realmente filtrada (con su propia paginación), en vez de reutilizar
    # result_line_ids (que siempre trae todo).
    result_line_ok_ids = fields.One2many(
        "ivess.invoice.import.result.line",
        "wizard_id",
        string="Facturas OK",
        domain=[("has_error", "=", False)],
    )
    result_line_error_ids = fields.One2many(
        "ivess.invoice.import.result.line",
        "wizard_id",
        string="Facturas con error",
        domain=[("has_error", "=", True)],
    )
    total_count = fields.Integer(string="Total", readonly=True)
    ok_count = fields.Integer(string="OK", readonly=True)
    error_count = fields.Integer(string="Errores", readonly=True)
    preview_show_errors = fields.Boolean(
        string="Mostrar errores",
        default=True,
        help="Controla si la previsualización muestra la lista de"
        " comprobantes OK o la de comprobantes con error.",
    )

    # ------------------------------------------------------------------
    # Paso 1 -> 2: leer archivo, agrupar y validar (no escribe account.move)
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Adjuntá un archivo para importar."))
        if openpyxl is None:
            raise UserError(
                _("Falta la librería 'openpyxl' en el servidor para leer archivos .xlsx.")
            )

        rows = self._read_excel_rows(base64.b64decode(self.file))
        groups = group_invoice_rows(rows)

        self.result_line_ids.unlink()
        for group in groups:
            self._create_preview_line(group)

        self.total_count = len(self.result_line_ids)
        self.error_count = len(self.result_line_ids.filtered("has_error"))
        self.ok_count = self.total_count - self.error_count
        self.preview_show_errors = True
        self.state = "preview"
        return self._reopen()

    def action_show_errors(self):
        self.ensure_one()
        self.preview_show_errors = True
        return self._reopen()

    def action_show_ok(self):
        self.ensure_one()
        self.preview_show_errors = False
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
                "name": "errores_import_facturas_%s.csv"
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
        # ';' como delimitador y BOM utf-8: así lo abre bien Excel en
        # configuración regional argentina (que usa ',' como separador
        # decimal, por lo que toma ',' como parte de los números en vez de
        # como separador de columnas si el CSV usara ',').
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                _("Comprobante"),
                _("Código cliente"),
                _("Razón social"),
                _("Documento"),
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
                    line.cliente_razon_social,
                    line.cliente_documento,
                    line.fecha or "",
                    line.importe_total,
                    (line.error_message or "").replace("\n", " | "),
                ]
            )
        return buffer.getvalue().encode("utf-8-sig")

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
        """Normaliza un valor numérico del Excel a float, tolerando que venga
        como número (int/float) o como texto con separador decimal ','
        (formato AR, ej. "1.234,56") o '.' (ej. "1234.56" o "1,234.56" con
        ',' de miles). Se usa para todas las columnas de importe/tasa
        (precio unitario, tasa de iva, tasa de iva no inscripto, importe iva
        inscripto/no inscripto, importe total neto del item, importe del
        renglón, montos y bases de impuestos internos/especiales, cantidad,
        importe total) para que no dependa de cómo haya venido formateada la
        celda en cada renglón."""
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(" ", "")
        if not text:
            raise ValueError("empty value")
        if "," in text and "." in text:
            if text.rindex(",") > text.rindex("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        return float(text)

    @staticmethod
    def _digits_to_int(value):
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return int(digits) if digits else None

    @classmethod
    def _to_numeric_str(cls, value):
        """Normaliza a una representación canónica sin ceros a la izquierda,
        sea que la celda venga como texto, número o número con formato
        distinto entre renglones (ej. "0004" vs 4 vs 4.0). Se usa para
        pto_vta/numero_comprob: son parte de la clave de agrupación de la
        factura y también se comparan contra el diario, así que deben
        comparar igual sin importar cómo vino la celda."""
        digits = cls._digits_to_int(cls._to_str(value))
        return str(digits) if digits is not None else ""

    @classmethod
    def _to_cae(cls, value):
        text = cls._to_str(value)
        return text if text and text != "0" else ""

    @staticmethod
    def _to_date(value):
        text = str(int(value)) if isinstance(value, float) else str(value).strip()
        return datetime.strptime(text, "%Y%m%d").date()

    def _read_excel_rows(self, content):
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            raise UserError(_("No se pudo leer el archivo como Excel: %s") % exc) from exc

        sheet = workbook.worksheets[0]
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            raise UserError(_("La primera hoja del archivo está vacía."))

        headers = [self._normalize_header(h) for h in header_row]
        missing_headers = [h for h in EXPECTED_HEADERS if h not in headers]
        if missing_headers:
            raise UserError(
                _("Faltan columnas en el archivo: %s") % ", ".join(missing_headers)
            )
        col_index = {h: i for i, h in enumerate(headers)}

        rows = []
        for row_number, raw_row in enumerate(
            sheet.iter_rows(min_row=2, values_only=True), start=2
        ):
            if all(cell is None for cell in raw_row):
                continue
            rows.append(self._row_to_dict(raw_row, col_index, row_number))
        return rows

    def _row_to_dict(self, raw_row, col_index, row_number):
        def cell(header):
            idx = col_index[header]
            return raw_row[idx] if idx < len(raw_row) else None

        return {
            "_row_number": row_number,
            "tipo_comprobante": self._to_str(cell("tipo de comprobante")).upper(),
            "letra": self._to_str(cell("letra")).upper(),
            "pto_vta": self._to_numeric_str(cell("pto vta")),
            "numero_comprob": self._to_numeric_str(cell("numero comprob")),
            "fecha": cell("fecha"),
            "cod_cliente": self._to_str(cell("cod cliente")),
            "razon_social": self._to_str(cell("razon social")),
            "documento": self._to_str(cell("documento")),
            "fecha_vto": cell("fecha vto"),
            "importe_total": cell("importe total"),
            "comprobante_anulado": self._to_str(cell("comprobante anulado")).upper() == "S",
            "cae": self._to_cae(cell("cae")),
            "vto_cae": cell("vto cae"),
            "tipo_item": self._to_str(cell("tipo de item")),
            "cod_art": self._to_str(cell("cod art")),
            "cantidad": cell("cantidad"),
            "precio_unitario": cell("precio unitario"),
            "tasa_iva": cell("tasa de iva"),
            "tasa_iva_no_inscripto": cell("tasa de iva no inscripto"),
            "importe_iva_inscripto": cell("importe iva inscripto"),
            "importe_iva_no_inscripto": cell("importe iva no inscripto"),
            "importe_total_neto_item": cell("importe total neto del item"),
            "importe_del_renglon": cell("importe del renglon"),
            "special_taxes": [
                {
                    "cod": self._to_str(cell(cod_header)),
                    "monto": cell(monto_header),
                    "base": cell(base_header) if base_header else None,
                }
                for cod_header, monto_header, base_header in SPECIAL_TAX_COLUMNS
            ],
        }

    # ------------------------------------------------------------------
    # Resolución de cada grupo contra Odoo (partner, tipo de comprobante,
    # productos, impuestos) y creación de las líneas de previsualización.
    # ------------------------------------------------------------------

    def _create_preview_line(self, group):
        if group.get("error"):
            self.env["ivess.invoice.import.result.line"].create(
                {
                    "wizard_id": self.id,
                    "tipo_comprobante": group["tipo_comprobante"],
                    "letra": group["letra"],
                    "pto_vta": group["pto_vta"],
                    "numero_comprobante": group["numero_comprob"],
                    "has_error": True,
                    "error_message": group["error"],
                }
            )
            return

        errors = []
        doc_type = TIPO_COMPROBANTE_DOC_TYPES.get(group["tipo_comprobante"])
        if not doc_type:
            errors.append(
                _(
                    "tipo de comprobante '%s' no soportado (esta versión solo"
                    " importa %s)."
                )
                % (
                    group["tipo_comprobante"],
                    ", ".join(sorted(TIPO_COMPROBANTE_DOC_TYPES)),
                )
            )

        voucher_type = self._find_voucher_type(group["letra"], doc_type)
        if not voucher_type:
            errors.append(
                _("No se encontró un tipo de comprobante Odoo para la letra '%s'.")
                % group["letra"]
            )

        journal, journal_candidates = self._find_journal(group["letra"], group["pto_vta"])
        if not journal:
            if journal_candidates:
                errors.append(
                    _(
                        "La letra '%s' + punto de venta '%s' coincide con %s"
                        " diarios de venta distintos; debe coincidir con uno"
                        " solo."
                    )
                    % (group["letra"], group["pto_vta"], journal_candidates)
                )
            else:
                errors.append(
                    _(
                        "No se encontró un diario de venta para la letra '%s'"
                        " + punto de venta '%s'."
                    )
                    % (group["letra"], group["pto_vta"])
                )

        partner = self._find_partner(group["cod_cliente"], group["documento"])
        if not partner:
            errors.append(
                _(
                    "No se encontró un cliente con código Bejerman '%s' ni con"
                    " CUIT/documento '%s' (%s)."
                )
                % (group["cod_cliente"], group["documento"], group["razon_social"])
            )

        try:
            fecha = self._to_date(group["fecha"]) if group["fecha"] else False
        except ValueError:
            fecha = False
            errors.append(_("Fecha inválida: '%s'.") % group["fecha"])

        fecha_vto = False
        if group["fecha_vto"]:
            try:
                fecha_vto = self._to_date(group["fecha_vto"])
            except ValueError:
                errors.append(_("Fecha de vencimiento inválida: '%s'.") % group["fecha_vto"])

        vto_cae = False
        if group["vto_cae"]:
            try:
                vto_cae = self._to_date(group["vto_cae"])
            except ValueError:
                errors.append(_("Vencimiento de CAE inválido: '%s'.") % group["vto_cae"])

        try:
            importe_total = self._to_float(group["importe_total"])
        except ValueError:
            importe_total = 0.0
            errors.append(_("Importe total inválido: '%s'.") % group["importe_total"])

        comprobante_ref = self._comprobante_ref(
            group["letra"], group["pto_vta"], group["numero_comprob"]
        )
        if partner:
            move_type = "out_refund" if group["tipo_comprobante"] == "NC" else "out_invoice"
            dedup_domain = [
                ("move_type", "=", move_type),
                ("ref", "=", comprobante_ref),
                ("partner_id", "=", partner.id),
            ]
            if move_type == "out_invoice":
                # FC y ND comparten move_type "out_invoice": distinguirlos por
                # is_debit_note para no confundir una con la otra en el dedup.
                dedup_domain.append(
                    ("is_debit_note", "=", group["tipo_comprobante"] == "ND")
                )
            existing = self.env["account.move"].search(dedup_domain, limit=1)
            if existing:
                errors.append(
                    _("Ya existe una factura importada con esta clave (account.move #%s).")
                    % existing.id
                )

        detail_vals, detail_errors = self._resolve_detail_lines(group["lines"])
        errors.extend(detail_errors)

        result_line = self.env["ivess.invoice.import.result.line"].create(
            {
                "wizard_id": self.id,
                "tipo_comprobante": group["tipo_comprobante"],
                "letra": group["letra"],
                "pto_vta": group["pto_vta"],
                "numero_comprobante": group["numero_comprob"],
                "comprobante_ref": comprobante_ref,
                "fecha": fecha,
                "fecha_vto": fecha_vto,
                "importe_total": importe_total,
                "comprobante_anulado": bool(group["comprobante_anulado"]),
                "cae": group["cae"],
                "vto_cae": vto_cae,
                "cliente_codigo": group["cod_cliente"],
                "cliente_razon_social": group["razon_social"],
                "cliente_documento": group["documento"],
                "partner_id": partner.id if partner else False,
                "voucher_type_id": voucher_type.id if voucher_type else False,
                "journal_id": journal.id if journal else False,
                "has_error": bool(errors),
                "error_message": "\n".join(errors) if errors else False,
                "detail_line_ids": detail_vals,
            }
        )
        return result_line

    @staticmethod
    def _comprobante_ref(letra, pto_vta, numero_comprob):
        """Clave de deduplicación/referencia externa del comprobante, en el
        mismo formato compuesto que usa el propio sistema origen (aguas) para
        identificar un comprobante (ver hoja "items" de sus exportes: letra +
        punto de venta + número). Se guarda en el campo nativo
        account.move.ref."""
        return "%s%s%s" % (letra, (pto_vta or "").zfill(4), (numero_comprob or "").zfill(8))

    def _find_voucher_type(self, letra, doc_type):
        if not letra or not doc_type:
            return None
        candidates = self.env["res.voucher.type"].search(
            [("doc_type", "=", doc_type), ("denomination", "=", letra.lower())]
        )
        if not candidates:
            return None
        # Puede haber más de un tipo para la misma letra (ej: "FACTURAS A",
        # "... CON LEYENDA RETENCIÓN", "... MiPyMEs FCE"). Sin una columna en
        # el Excel que distinga el caso especial, se asume el comprobante
        # "plano" (menor afip_code) como default razonable para una
        # importación masiva estándar.
        return candidates.sorted(key=lambda v: v.afip_code)[0]

    def _find_journal(self, letra, pto_vta):
        """Resuelve el diario de ventas a partir de la letra + punto de venta
        del Excel (columnas "letra" y "pto vta"): el archivo mezcla
        comprobantes de más de un diario, así que el diario ya no se elige a
        mano en el wizard. Un mismo punto de venta AFIP puede tener un
        diario Odoo distinto por letra (ej. "FACTURAS A 0001" vs "FACTURAS B
        0001"), así que primero se filtra por account.journal.denomination
        (igual que res.voucher_type.denomination en _find_voucher_type) y
        recién ahí se matchea el número: contra el código AFIP del diario
        (account.journal.code, ver get_pos_number() en l10n_ar_eynes) o, si
        no coincide con ninguno, contra los dígitos del nombre del diario
        (algunos diarios están identificados solo por su nombre: el campo
        "code" puede no tener nada que ver con el punto de venta real, ej.
        un diario "9999" con code="INV1"). NO existe account.journal.
        l10n_ar_afip_pos_number en esta instalación: el módulo Odoo
        oficial "l10n_ar" está desinstalado, solo corre "l10n_ar_eynes"
        (fork propio), que no tiene ese campo.

        :return: tupla (diario o None, cantidad de diarios candidatos).
        """
        pos_number = self._digits_to_int(pto_vta)
        if not letra or pos_number is None:
            return None, 0
        journals = self.env["account.journal"].search(
            [
                ("type", "=", "sale"),
                ("company_id", "=", self.env.company.id),
                ("denomination", "=", letra.lower()),
            ]
        )
        matches = journals.filtered(
            lambda j: j.get_pos_number() == pos_number
            or self._digits_to_int(j.name) == pos_number
        )
        return (matches[0] if len(matches) == 1 else None), len(matches)

    @staticmethod
    def _only_digits(value):
        return "".join(ch for ch in (value or "") if ch.isdigit())

    def _find_partner(self, cod_cliente, documento):
        """Resuelve el cliente por su código Bejerman (columna "cod cliente"
        del Excel, matcheado contra res.partner.codigo_bejerman) y, si no
        matchea, por CUIT/documento (res.partner.vat) como respaldo."""
        if cod_cliente:
            candidates = self.env["res.partner"].search(
                [("codigo_bejerman", "=", cod_cliente)]
            )
            if len(candidates) == 1:
                return candidates[0]

        digits = self._only_digits(documento)
        if not digits:
            return None
        candidates = self.env["res.partner"].search([("vat", "=", digits)])
        return candidates[0] if len(candidates) == 1 else None

    def _find_tax(self, tasa_iva, company):
        candidates = self.env["account.tax"].search(
            [("type_tax_use", "=", "sale"), ("company_id", "=", company.id)]
        )
        candidates = candidates.filtered(lambda t: round(t.amount, 2) == round(tasa_iva, 2))
        return candidates[0] if len(candidates) == 1 else None, len(candidates)

    def _resolve_detail_lines(self, lines):
        detail_vals = []
        errors = []
        company = self.env.company

        if not lines:
            errors.append(_("La factura no tiene líneas de detalle."))
            return detail_vals, errors

        for line in lines:
            line_errors = []

            try:
                cantidad = self._to_float(line["cantidad"])
            except (TypeError, ValueError):
                cantidad = 0.0
                line_errors.append(_("Cantidad inválida: '%s'.") % line["cantidad"])

            try:
                precio_unitario = self._to_float(line["precio_unitario"])
            except (TypeError, ValueError):
                precio_unitario = 0.0
                line_errors.append(_("Precio unitario inválido: '%s'.") % line["precio_unitario"])

            try:
                tasa_iva = self._to_float(line["tasa_iva"])
            except (TypeError, ValueError):
                tasa_iva = 0.0
                line_errors.append(_("Tasa de IVA inválida: '%s'.") % line["tasa_iva"])

            try:
                tasa_iva_no_inscripto = self._to_float(line["tasa_iva_no_inscripto"])
            except (TypeError, ValueError):
                tasa_iva_no_inscripto = 0.0
            if tasa_iva_no_inscripto:
                line_errors.append(
                    _("Tasa de IVA no inscripto (%.2f) no soportada en esta versión.")
                    % tasa_iva_no_inscripto
                )

            product = self._find_product(line["cod_art"])
            if not product:
                line_errors.append(
                    _("No se encontró un producto con código de artículo '%s'.")
                    % line["cod_art"]
                )

            # Tasa de IVA 0: la línea no lleva impuesto de IVA (tax_id queda
            # vacío), no se busca ni exige que exista una tasa "0%" en Odoo.
            tax = None
            if not line_errors and tasa_iva:
                tax, tax_candidates = self._find_tax(tasa_iva, company)
                if not tax:
                    line_errors.append(
                        _("No se encontró (o es ambigua, %s candidatos) la tasa de IVA %.2f%%.")
                        % (tax_candidates, tasa_iva)
                    )

            try:
                importe_total_neto_item = self._to_float(line["importe_total_neto_item"])
            except (TypeError, ValueError):
                importe_total_neto_item = 0.0

            try:
                importe_iva_inscripto = self._to_float(line["importe_iva_inscripto"])
            except (TypeError, ValueError):
                importe_iva_inscripto = 0.0

            try:
                importe_iva_no_inscripto = self._to_float(line["importe_iva_no_inscripto"])
            except (TypeError, ValueError):
                importe_iva_no_inscripto = 0.0

            special_tax_vals, special_tax_errors = self._resolve_special_taxes(
                line["special_taxes"]
            )
            line_errors.extend(special_tax_errors)

            try:
                importe_del_renglon = self._to_float(line["importe_del_renglon"])
            except (TypeError, ValueError):
                importe_del_renglon = 0.0

            detail_vals.append(
                (
                    0,
                    0,
                    {
                        "tipo_item": line["tipo_item"],
                        "cod_art": line["cod_art"],
                        "product_id": product.id if product else False,
                        "cantidad": cantidad,
                        "precio_unitario": precio_unitario,
                        "tasa_iva": tasa_iva,
                        "tax_id": tax.id if tax else False,
                        "importe_total_neto_item": importe_total_neto_item,
                        "importe_iva_inscripto": importe_iva_inscripto,
                        "importe_iva_no_inscripto": importe_iva_no_inscripto,
                        "importe_del_renglon": importe_del_renglon,
                        "special_tax_ids": special_tax_vals,
                        "has_error": bool(line_errors),
                        "error_message": "; ".join(line_errors) if line_errors else False,
                    },
                )
            )
            errors.extend(line_errors)

        return detail_vals, errors

    def _resolve_special_taxes(self, special_taxes):
        """Resuelve las columnas de impuesto especial/interno de una línea
        (ver SPECIAL_TAX_COLUMNS): cada una matchea por separado contra un
        impuesto Odoo (ver _find_special_tax) y aporta su propio monto y
        base imponible. "cod impuesto interno" no trae columna de base en el
        Excel y el impuesto interno no tiene base imponible: su base se
        informa siempre en 0."""
        special_tax_vals = []
        errors = []

        for slot in special_taxes:
            cod = slot["cod"]
            if not cod:
                continue

            try:
                monto = self._to_float(slot["monto"])
            except (TypeError, ValueError):
                monto = 0.0

            has_base_column = slot["base"] is not None
            base = 0.0
            if has_base_column:
                try:
                    base = self._to_float(slot["base"])
                except (TypeError, ValueError):
                    base = 0.0

            special_tax = self._find_special_tax(cod)
            if not special_tax:
                errors.append(
                    _(
                        "No se encontró un mapeo para el código de impuesto"
                        " especial '%s' (configuralo en Contabilidad >"
                        " Configuración > Códigos de impuesto especial"
                        " (importación))."
                    )
                    % cod
                )
                continue
            if not monto or (has_base_column and not base):
                errors.append(
                    _(
                        "El código de impuesto especial '%s' está mapeado a"
                        " '%s' pero el monto%s informado es 0."
                    )
                    % (
                        cod,
                        special_tax.name,
                        _(" o la base") if has_base_column else "",
                    )
                )
                continue

            special_tax_vals.append(
                (0, 0, {"cod": cod, "tax_id": special_tax.id, "monto": monto, "base": base})
            )

        return special_tax_vals, errors

    def _find_special_tax(self, cod_impuesto_especial):
        company = self.env.company
        # 1) Percepciones: se matchean directo contra el código Bejerman
        # cargado en el propio impuesto (Contabilidad > Impuestos > pestaña
        # "Perceptions").
        perception = self.env["account.tax"].search(
            [
                ("bejerman_code", "=", cod_impuesto_especial),
                ("tax_group_id.group_type", "=", "perception"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if perception:
            return perception
        # 2) Impuestos internos (u otras percepciones sin código Bejerman
        # cargado todavía): mapeo manual configurable.
        mapping = self.env["ivess.invoice.import.tax.code"].search(
            [
                ("code", "=", cod_impuesto_especial),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        return mapping.tax_id if mapping else None

    def _find_product(self, cod_art):
        if not cod_art:
            return None
        candidates = self.env["product.product"].search([("default_code", "=", cod_art)])
        return candidates[0] if len(candidates) == 1 else None

    # ------------------------------------------------------------------
    # Paso 2 -> 3: crear las facturas que no tengan error
    # ------------------------------------------------------------------

    def action_confirm(self):
        self.ensure_one()
        for result_line in self.result_line_ids:
            if result_line.has_error:
                result_line.resultado = "error"
                continue
            try:
                with self.env.cr.savepoint():
                    move = self._create_move(result_line)
                    move.action_post()
                    if result_line.comprobante_anulado:
                        move.button_cancel()
                result_line.write({"resultado": "ok", "odoo_move_id": move.id})
            except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
                result_line.write(
                    {
                        "resultado": "error",
                        "has_error": True,
                        "error_message": _("Error al crear la factura: %s") % exc,
                    }
                )

        self.ok_count = len(self.result_line_ids.filtered(lambda r: r.resultado == "ok"))
        self.error_count = len(self.result_line_ids.filtered(lambda r: r.resultado == "error"))
        self.state = "done"
        return self._reopen()

    def _create_move(self, result_line):
        invoice_wide_tax_ids = self._invoice_wide_special_tax_ids(result_line)
        line_vals = [
            (
                0,
                0,
                {
                    "product_id": detail.product_id.id,
                    "name": detail.product_id.display_name,
                    "quantity": detail.cantidad,
                    "price_unit": detail.precio_unitario,
                    "tax_ids": [
                        (6, 0, self._line_tax_ids(detail, invoice_wide_tax_ids))
                    ],
                },
            )
            for detail in result_line.detail_line_ids
        ]
        move_vals = {
            "move_type": "out_refund" if result_line.tipo_comprobante == "NC" else "out_invoice",
            "journal_id": result_line.journal_id.id,
            "partner_id": result_line.partner_id.id,
            "voucher_type_id": result_line.voucher_type_id.id,
            "invoice_date": result_line.fecha,
            "invoice_line_ids": line_vals,
            "ref": result_line.comprobante_ref,
            "cae": result_line.cae or False,
            "cae_due_date": result_line.vto_cae or False,
            # Esta es una factura histórica, ya emitida y numerada en el
            # sistema origen (con CAE propio): se fija el número real acá en
            # vez de dejar que se autonumere con la secuencia del diario.
            # posted_before=True es lo que l10n_ar_eynes chequea en
            # account.move._post() para no pisar internal_number con el
            # próximo valor de la secuencia (ver l10n_ar_eynes/models/
            # account_move.py).
            "internal_number": self._internal_number(
                result_line.pto_vta, result_line.numero_comprobante
            ),
            "posted_before": True,
            # Las percepciones/impuestos internos de esta factura ya vienen
            # calculados del sistema origen (columnas "monto imp interno" /
            # "monto imp especiales*"): no queremos que l10n_ar_eynes intente
            # recalcularlos solo con la posición fiscal del cliente.
            "disable_perceptions": True,
        }
        if result_line.tipo_comprobante == "ND":
            move_vals["is_debit_note"] = True
        if result_line.fecha_vto:
            move_vals["invoice_date_due"] = result_line.fecha_vto
        perception_vals, internal_tax_vals = self._special_tax_vals(result_line)
        if perception_vals:
            move_vals["perception_ids"] = perception_vals
        if internal_tax_vals:
            move_vals["internal_taxes_ids"] = internal_tax_vals

        move = self.env["account.move"].create(move_vals)
        # account.move.line.tax_ids es un compute (store=True) que se
        # recalcula por el solo hecho de tener product_id seteado (ver
        # AccountMoveLine._get_computed_taxes() en l10n_ar_eynes: agrega ahí
        # los impuestos internos por defecto de la posición fiscal del
        # cliente a CUALQUIER línea de producto, sin mirar detail_line_ids).
        # Para que cada línea quede EXACTAMENTE con los impuestos que
        # matcheamos para ella arriba (ni de más por ese compute, ni de
        # menos), se reescribe tax_ids explícito después del create(): un
        # write() de tax_ids solo no depende de product_id/product_uom_id,
        # así que no dispara ese compute de nuevo.
        for line, detail in zip(
            move.invoice_line_ids.filtered(lambda l: l.display_type == "product"),
            result_line.detail_line_ids,
        ):
            line.tax_ids = [(6, 0, self._line_tax_ids(detail, invoice_wide_tax_ids))]
        # perception_ids/internal_taxes_ids por sí solos solo alimentan las
        # pestañas "Percepciones"/"Internal taxes": el importe informado ahí
        # también tiene que quedar como monto de la línea de impuesto real
        # del asiento (generada por Odoo a partir del tax_ids de cada línea,
        # reescrito arriba). NO se usan acá los helpers
        # link_perception_to_move_lines()/link_internal_taxes_to_move_lines()
        # de l10n_ar_eynes: con disable_perceptions=True esos recalculan la
        # aplicabilidad de percepciones por posición fiscal/cuenta contable
        # y las aplican a TODAS las líneas de producto sin distinguir
        # percepción de IVA (por línea) de percepción IIBB (toda la
        # factura); acá se arma explícito el tax_ids correcto por línea
        # (ver _line_tax_ids) tal como matcheamos arriba.
        if perception_vals:
            move._update_perception_move_line_amount()
        if internal_tax_vals:
            move._update_internal_taxes_move_line_amount()
        return move

    @staticmethod
    def _invoice_wide_special_tax_ids(result_line):
        """IDs de los impuestos especiales que aplican a TODA la factura y
        no solo a la línea del Excel donde se detectaron: las percepciones
        de IIBB (ARBA/AGIP-CABA, account.tax.retention_type ==
        "gross_income"). A diferencia del impuesto interno y la percepción
        de IVA (que sí son por línea de producto), IIBB se calcula sobre el
        neto de toda la factura, así que su tax_id debe quedar en el
        tax_ids de todas las líneas de producto del asiento (ver
        _line_tax_ids) para que Odoo calcule bien la base de esa línea de
        impuesto (tax_base_amount / tax_totals)."""
        special_taxes = result_line.detail_line_ids.mapped("special_tax_ids")
        return special_taxes.filtered(
            lambda s: s.tax_id.retention_type == "gross_income"
        ).tax_id.ids

    @staticmethod
    def _line_tax_ids(detail, invoice_wide_tax_ids):
        """IDs de impuesto a asignar a una línea de producto del asiento: su
        IVA (si tiene: con tasa de IVA 0 la línea no lleva tax_id de IVA),
        sus impuestos especiales/internos propios que NO sean IIBB (impuesto
        interno y percepción de IVA: van por línea, ver
        _resolve_special_taxes) y las percepciones IIBB de toda la factura
        (invoice_wide_tax_ids, ver _invoice_wide_special_tax_ids)."""
        per_line_tax_ids = detail.special_tax_ids.filtered(
            lambda s: s.tax_id.retention_type != "gross_income"
        ).tax_id.ids
        iva_tax_ids = [detail.tax_id.id] if detail.tax_id else []
        return list(dict.fromkeys(iva_tax_ids + per_line_tax_ids + invoice_wide_tax_ids))

    @staticmethod
    def _internal_number(pto_vta, numero_comprobante):
        # Se arma con el "pto vta" tal como vino del Excel (ya validado
        # contra el diario en _find_journal), NO releyendo el diario: los
        # campos de punto de venta del diario (account.journal.code) pueden
        # no tener relación con el punto de venta real (ver comentario en
        # _find_journal, ej. diario "9999" con code="INV1"). Mismo padding
        # que _comprobante_ref/comprobante_display (zfill(4) en el punto de
        # venta), ya que replica el formato compuesto del sistema origen.
        return "%s-%s" % (
            (pto_vta or "").zfill(4),
            (numero_comprobante or "").zfill(8),
        )

    @staticmethod
    def _special_tax_vals(result_line):
        """Agrega, por impuesto especial resuelto (percepción IIBB/IVA,
        impuesto interno), una línea a perception_ids o internal_taxes_ids
        con base y monto sumados de todas las líneas de detalle que
        comparten ese impuesto (no se recalculan: se toman tal cual del
        archivo origen)."""
        perception_vals = []
        internal_tax_vals = []
        special_lines = result_line.detail_line_ids.mapped("special_tax_ids")
        for tax in special_lines.mapped("tax_id"):
            lines = special_lines.filtered(lambda s, tax=tax: s.tax_id == tax)
            base = sum(lines.mapped("base"))
            amount = sum(lines.mapped("monto"))
            if tax.tax_group_id.group_type == "internals":
                internal_tax_vals.append(
                    (
                        0,
                        0,
                        {
                            # "name" es un campo compute/store, pero el compute no
                            # se dispara de forma confiable al crear vía comandos
                            # (0,0,{...}) anidados en account.move.create(): se
                            # informa explícito, igual que hace l10n_ar_eynes.
                            "name": tax.name,
                            "tax_id": tax.id,
                            "base": base,
                            "amount": amount,
                        },
                    )
                )
            else:
                perception_vals.append(
                    (
                        0,
                        0,
                        {
                            "name": tax.name,
                            "perception_id": tax.id,
                            "partner_id": result_line.partner_id.id,
                            "base": base,
                            "amount": amount,
                        },
                    )
                )
        return perception_vals, internal_tax_vals
