from odoo import models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def create_pos_sequence(self):
        # NOTA: este fix conviene llevarlo a l10n_ar_eynes
        # (account.journal.create_pos_sequence). Ahí se crean las secuencias
        # con ir.sequence.create() sin sudo, y ir.sequence solo permite crear
        # a base.group_system. Se usa sudo solo para crear las secuencias del
        # diario; el write posterior sobre el diario sigue con el usuario
        # actual, y los permisos de ir.sequence no se amplían.
        return super(AccountJournal, self.sudo()).create_pos_sequence()
