##############################################################################
#
#   Copyright (c) 2026 Eynes SRL  (Eynes - Ingenieria del software)
#   License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
#
##############################################################################

import re
import time
from decimal import Decimal

from odoo import _, api, models

from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width import moneyfmt


class CreateArcibaFiles(models.TransientModel):
    _inherit = "create.arciba.files"

    # [T16864] Copia de _get_ret_data de l10n_ar_eynes. Lo que se informa en
    # el TXT no cambia. Cambios (marcados con [T16864]): no se exige factura
    # imputada a la OP (sin lineas de deuda el total del comprobante es el
    # importe de la OP), y los problemas dejan de bloquear el archivo: se
    # devuelven como avisos junto con las lineas validas.
    @api.model
    def _collect_ret_data(self, retention_ids):
        """Retentions to export and warnings (non-blocking problems).

        Returns (lines, warnings).
        """
        ret_obj = self.env["account.payment.order.retention.line"]
        res = []
        errors = []
        for ret in ret_obj.browse(retention_ids):
            # **-------**  Datos desde la Retención: **--------**
            # Ret Date
            date_val = time.strptime(
                str(ret.date), "%Y-%m-%d"
            )  # String(YYYY-MM-DD)->Datetime
            date_val = time.strftime(
                "%d/%m/%Y", date_val
            )  # Datetime->String: dd/mm/yyyy
            # Nro Cert
            nro_cert_propio = ret.certificate_no or "0000000000000000"
            # Ret / Per applied
            ret_per_applied = ret.amount
            # Ret / Per base
            base_amount = ret.base_amount

            # **-------**  Datos desde la Orden de Pago: **--------**
            op = ret.payment_order_id
            partner = op.partner_id
            # Alicuota
            percentage = (
                self.env["res.partner.retention"]
                .search(
                    [
                        ("retention_id", "=", ret.retention_id.id),
                        ("partner_id", "=", partner.id),
                        ("period", "=", self.period_start),
                    ]
                )
                .percent
            )
            if percentage < 0 or percentage > 99.99:
                errors.append(
                    _(
                        "rtl #%(ret_id)s: Percentage cannot be negative or "
                        "more than 99.99 (%(ret_name)s) (OP ID %(op_id)s)",
                        ret_id=ret.id,
                        ret_name=ret.name,
                        op_id=ret.voucher_number,
                    )
                )
                continue
            elif percentage != 0.0:
                # Type of document partner
                nro_doc_retenido = (
                    partner.vat.replace("-", "") if partner.vat else "00000000000"
                )
                try:
                    tipo_doc_retenido = self._get_partner_document_type_code(partner)
                except Exception as e:
                    errors.append(str(e))
                    continue
                # Voucher date
                voucher_date = time.strptime(
                    str(op.date), "%Y-%m-%d"
                )  # String(YYYY-MM-DD)->Datetime
                voucher_date = time.strftime(
                    "%d/%m/%Y", voucher_date
                )  # Datetime->String: dd/mm/yyyy
                # Internal number
                voucher_number = re.sub(r"\D", "", op.number)
                # Partner Data
                pos_fiscal_retenido = partner.property_account_position_id.afip_code
                if pos_fiscal_retenido in [
                    self.env.ref("l10n_ar_eynes.fiscal_position_rem").afip_code,
                    self.env.ref("l10n_ar_eynes.fiscal_position_ms").afip_code,
                ]:
                    pos_fiscal_retenido = 4
                elif pos_fiscal_retenido in [
                    self.env.ref("l10n_ar_eynes.fiscal_position_se").afip_code,
                ]:
                    pos_fiscal_retenido = 3
                else:
                    pos_fiscal_retenido = 1

                razon_social_retenido = (
                    (partner.name).replace("ñ", "n").replace("Ñ", "N")
                )
                # IIBB
                ppids = partner.retention_ids
                ret_tax = ret.retention_id
                ret_partner = ppids.filtered(
                    lambda x, ret_tax=ret_tax: x.retention_id == ret_tax
                )
                ret_partner = ret_partner[0] if len(ret_partner) > 1 else ret_partner
                sit_iibb = self._get_partner_iibb_code(ret_partner.sit_iibb)
                if not sit_iibb:
                    errors.append(
                        _(
                            "rtl #%(ret_id)s: IIBB Situation cannot be empty"
                            " (%(ret_name)s) (Partner %(part_name)s)",
                            ret_id=ret.id,
                            ret_name=ret.name,
                            part_name=razon_social_retenido,
                        )
                    )

                # **-------**  Datos desde las Facturas: **--------**
                op_lines = op.debt_line_ids.filtered(lambda line: line.amount != 0)
                # [T16864] Un pago a cuenta no tiene facturas imputadas, pero
                # la retencion igual se informa: las facturas no aportan
                # ningun dato al registro (IVA en 0.0 y letra vacia). Se
                # quita el rechazo que bloqueaba la generacion del archivo.
                # Denomination
                denomination_name = ""
                # Invoice total
                # [T16864] Sin lineas de deuda (pago a cuenta) el total del
                # comprobante es el importe de la propia OP.
                op_amount_total = sum(op_lines.mapped("amount")) or op.amount
                # Iva Amount
                inv_iva_amount = 0.0
                # # Monto de otros conceptos:
                amount_others = op_amount_total - inv_iva_amount - base_amount
                # [T16864] Solo aviso: no cambia lo que se informa.
                effective_percentage = (
                    round(ret_per_applied / base_amount * 100, 2)
                    if base_amount
                    else 0.0
                )
                if abs(effective_percentage - percentage) > 0.05:
                    errors.append(
                        _(
                            "rtl #%(ret_id)s: informed rate %(informed).2f%% "
                            "does not match the amount withheld over the "
                            "informed base (%(real).2f%%); the withholding was "
                            "calculated on base %(calc_base).2f, informed "
                            "base %(base).2f (OP %(op)s, %(partner)s)",
                            ret_id=ret.id,
                            informed=percentage,
                            real=effective_percentage,
                            calc_base=ret.base,
                            base=base_amount,
                            op=op.number,
                            partner=partner.display_name,
                        )
                    )

                line = {
                    "type": 1,  # Retention
                    "codigo_norma": 29,  # NUEVO: PADRÓN DE REGIMENES GENERALES
                    "fecha": date_val,
                    # Account Voucher (We pay to supplier)
                    "tipo_comp_origen_retenc": "03",
                    "letra_comprobante": denomination_name,
                    "numero_comprobante": voucher_number,
                    "fecha_comprobante": voucher_date,
                    "monto_comprobante": moneyfmt(
                        Decimal(op_amount_total), places=2, ndigits=13, dp=","
                    ),
                    "nro_cert_propio": str(nro_cert_propio),
                    "tipo_doc_retenido": tipo_doc_retenido,
                    "nro_doc_retenido": nro_doc_retenido,
                    # 'sit_iibb_retenido': sit_iibb,
                    "sit_iibb_retenido": 2,
                    "nro_insc_iibb_retenido": nro_doc_retenido,
                    "pos_fiscal_retenido": pos_fiscal_retenido,
                    "razon_social_retenido": razon_social_retenido,
                    "importe_otros_conceptos": moneyfmt(
                        Decimal(amount_others), places=2, ndigits=13, dp=","
                    ),
                    "importe_iva": moneyfmt(
                        Decimal(inv_iva_amount), places=2, ndigits=13, dp=","
                    ),
                    "monto_sujeto_a_ret_per": moneyfmt(
                        Decimal(base_amount), places=2, ndigits=13, dp=","
                    ),
                    "alicuota": moneyfmt(
                        Decimal(percentage), places=2, ndigits=4, dp=","
                    ),
                    "ret_per_aplicada": moneyfmt(
                        Decimal(ret_per_applied), places=2, ndigits=13, dp=","
                    ),
                    "monto_total_ret_per": moneyfmt(
                        Decimal(ret_per_applied), places=2, ndigits=13, dp=","
                    ),
                    "aceptacion": "",  # Para comprobantes mipyme
                    "fecha_aceptacion": "",  # Para comprobantes mipyme
                }
                res.append(line)
            else:
                # [T16864] Solo aviso: sin alicuota en el padron la
                # retencion se omite del archivo (igual que antes), pero
                # ahora se notifica.
                errors.append(
                    _(
                        "rtl #%(ret_id)s: left out of the file, the partner "
                        "has no rate for the period (OP %(op)s, %(partner)s)",
                        ret_id=ret.id,
                        op=op.number,
                        partner=partner.display_name,
                    )
                )
        return res, errors

    @api.model
    def _add_arciba_notes(self, title, informed, total, warnings):
        """Accumulate non-blocking warnings in the wizard notes."""
        if not warnings or not self:
            return
        lines = [f"{title}: {informed}/{total}"] + list(warnings)
        notes = self.notes + "\n\n" if self.notes else ""
        self.write({"notes": notes + "\n".join(lines)})

    @api.model
    def _get_ret_data(self, retention_ids):
        """[T16864] Problems are warnings: the valid lines are always returned."""
        lines, warnings = self._collect_ret_data(retention_ids)
        self._add_arciba_notes(
            _("Retentions informed"), len(lines), len(retention_ids), warnings
        )
        return None, lines

    @api.model
    def _get_perc_data(self, perc_ids):
        """[T16864] Problems are warnings: the valid lines are always returned."""
        status, payload = super()._get_perc_data(perc_ids)
        if not status:
            return status, payload
        # El original descarta todo si una percepcion falla: se vuelve a
        # pedir de a una para quedarse con las validas.
        lines, warnings = [], []
        for perc_id in perc_ids:
            status, payload = super()._get_perc_data([perc_id])
            if status:
                warnings.extend(payload)
            else:
                lines.extend(payload)
        self._add_arciba_notes(
            _("Perceptions informed"), len(lines), len(perc_ids), warnings
        )
        return None, lines

    def generate_fw_file(self, data_lst):
        """[T16864] The file is always generated; warnings are shown apart.

        Works for both create_files flows (l10n_ar_eynes and
        l10n_ar_eynes_internal_voucher), which return what this method returns.
        """
        res = super().generate_fw_file(data_lst)
        notes = self.notes
        if not notes:
            return res
        generated = self.env["arciba.generated.files"].search(
            [("company_id", "=", self.company_id.id)], order="id desc", limit=1
        )
        generated.notes = notes
        self.notes = False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("eARCIBA file generated with warnings"),
                "message": _(
                    "Some records were left out or need review. See the "
                    "Warnings of the generated file %(code)s before "
                    "submitting it to ARCIBA.",
                    code=generated.code,
                ),
                "type": "warning",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
