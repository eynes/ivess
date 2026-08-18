import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    padron_update_error = fields.Text(
        string="Padron Update Error",
        readonly=True,
        copy=False,
    )

    def do_update_from_padron(self, *args, **kwargs):
        partner_ids = self.env.context.get("active_ids")
        try:
            result = super().do_update_from_padron(*args, **kwargs)
        except Exception as error:
            if not partner_ids:
                raise
            _logger.exception(
                "Error fetching Padron values for partners %s", partner_ids
            )
            partners = self.env["res.partner"].browse(partner_ids)
            partners.write({"padron_update_error": str(error)})
            for partner in partners:
                partner.message_post(
                    body=_("Error al actualizar el Padrón de Perc/Ret: %s")
                    % error,
                )
            return False

        if partner_ids:
            partners = self.env["res.partner"].browse(partner_ids)
            partners.write({"padron_update_error": False})
            for partner in partners:
                partner.message_post(
                    body=_("Padrón de Perc/Ret actualizado correctamente. %s", result.get('params').get('message')),
                )
        return result
