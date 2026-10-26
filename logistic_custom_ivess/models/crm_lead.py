from odoo import models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_consult_zone(self):
        """Abre "Consultar zona" con la dirección del lead ya cargada."""
        self.ensure_one()
        wizard = self.env['zone.consult.wizard'].create({
            'street': self.street,
            'city': self.city,
            'state_id': self.state_id.id or self.env['zone.consult.wizard']._default_state().id,
        })
        return wizard._reopen()
