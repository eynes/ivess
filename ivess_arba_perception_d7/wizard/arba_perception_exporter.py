from odoo import models


class ArbaPerceptionExporterWizard(models.TransientModel):
    _inherit = 'arba.perception.exporter.wizard'

    def _get_arba_filename(self):
        filename = super()._get_arba_filename()
        return filename.replace('-P7-', '-D7-')
