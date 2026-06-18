from odoo import models, fields

class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    print_format = fields.Selection(
        selection_add=[('4x6', '4 x 6 (IVESS)')],
        ondelete={'4x6': 'set default'}
    )

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()
        if self.print_format == '4x6':
            xml_id = 'custom_ivess_product.action_report_etiqueta_personalizada'
            picking_id = self.env.context.get('active_model') == 'stock.picking' and self.env.context.get('active_id')
            data['custom_picking_id'] = picking_id
        return xml_id, data
