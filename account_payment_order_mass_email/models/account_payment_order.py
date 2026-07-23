from odoo import _, models
from odoo.exceptions import UserError


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def _get_mass_email_template_and_attachments(self):
        """Same template/attachment resolution logic as ``send_email``,
        duplicated here so the original module stays untouched."""
        self.ensure_one()
        IrAttachment = self.env["ir.attachment"]

        if self.type == "payment":
            payment_order_name = "Órden de Pago"
            template = self.env.ref(
                "l10n_ar_eynes.mail_template_data_payment_order_suppliers"
            )
        else:
            payment_order_name = "Recibo"
            template = self.env.ref("l10n_ar_eynes.mail_template_data_payment_order")

        payment_order_pdf = IrAttachment.search(
            [
                ("res_model", "=", "account.payment.order"),
                ("res_id", "=", self.id),
                ("name", "=", payment_order_name),
            ],
            order="create_date desc",
            limit=1,
        )
        retention_certificate_pdf = IrAttachment.search(
            [
                ("res_model", "=", "account.payment.order"),
                ("res_id", "=", self.id),
                ("name", "=", "Certificado de retención"),
            ],
            order="create_date desc",
            limit=1,
        )

        if not payment_order_pdf:
            payment_order_pdf = self.render_report(
                payment_order_name, "action_print_payment_order_qweb"
            )

        attachments = [payment_order_pdf.id]

        if (
            not retention_certificate_pdf
            and self.type == "payment"
            and len(self.retention_ids) > 0
        ):
            retention_certificate_pdf = self.render_report(
                "Certificado de retención",
                "action_print_retention_certificate_qweb",
            )
        if retention_certificate_pdf:
            attachments.append(retention_certificate_pdf.id)

        return template, attachments

    def action_send_email_mass(self):
        if not self:
            raise UserError(_("Seleccione al menos una orden de pago."))

        valid_orders = self.filtered(lambda order: order.state == "posted")
        invalid_orders = self - valid_orders

        for order in valid_orders:
            template, attachments = order._get_mass_email_template_and_attachments()
            template.send_mail(
                order.id,
                force_send=True,
                email_values={"attachment_ids": [(6, 0, attachments)]},
                email_layout_xmlid="mail.mail_notification_light",
            )

        if invalid_orders:
            message = _(
                "Se enviaron %(sent)s email(s). Se omitieron las siguientes "
                "órdenes por no estar validadas: %(numbers)s.",
                sent=len(valid_orders),
                numbers=", ".join(invalid_orders.mapped("number")),
            )
            notification_type = "warning" if valid_orders else "danger"
        else:
            message = _("Se enviaron %s email(s).", len(valid_orders))
            notification_type = "success"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Enviar órdenes de pago por email"),
                "message": message,
                "type": notification_type,
                "sticky": bool(invalid_orders),
            },
        }
