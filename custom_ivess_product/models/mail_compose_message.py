from odoo import models, api

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.model
    def default_get(self, fields_list):
        res = super(MailComposeMessage, self).default_get(fields_list)
        active_model = self._context.get('default_model') or res.get('model')
        if active_model == 'stock.request.order' and 'template_id' in fields_list:
            template = self.env['mail.template'].search([
                ('is_default_for_stock_request', '=', True),
                ('model', '=', 'stock.request.order') # Filtro de seguridad
            ], limit=1)

            if template:
                res['template_id'] = template.id

                # Opcional pero recomendado: Al forzar la plantilla en el default_get,
                # a veces es útil llamar al onchange para que te cargue el Asunto y el Cuerpo
                # automáticamente antes de que se renderice la vista.
                # compose_dummy = self.new(res)
                # En Odoo 19, los métodos de onchange en el composer suelen estar manejados
                # por campos computados. Si ves que la plantilla se asigna pero el cuerpo
                # queda vacío, puedes forzar los valores así:
                template_values = template._generate_template(
                    [res.get('res_id') or self._context.get('active_id')],
                    ['subject', 'body_html']
                ).get(res.get('res_id') or self._context.get('active_id'), {})

                if template_values.get('subject'):
                    res['subject'] = template_values['subject']
                if template_values.get('body_html'):
                    res['body'] = template_values['body_html']

        return res
