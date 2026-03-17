from odoo import models, fields, api
from odoo.exceptions import ValidationError

class MailTemplate(models.Model):
    _inherit = 'mail.template'

    is_default_for_stock_request = fields.Boolean(
        string='Por defecto para Stock Request',
        default=False,
        help="Si está marcado, esta plantilla se autoseleccionará en el wizard del chatter de stock.request.order"
    )

    @api.constrains('is_default_for_stock_request', 'model_id')
    def _check_unique_default_stock_request(self):
        for template in self:
            if template.is_default_for_stock_request:
                if template.model != 'stock.request.order':
                    raise ValidationError("El check de 'Por defecto' solo puede aplicarse a plantillas del modelo Stock Request.")
                duplicates_count = self.search_count([
                    ('is_default_for_stock_request', '=', True),
                    ('id', '!=', template.id)
                ])
                if duplicates_count > 0:
                    raise ValidationError("Ya existe otra plantilla marcada por defecto para Stock Request. Debes desmarcar la anterior antes de activar esta.")
