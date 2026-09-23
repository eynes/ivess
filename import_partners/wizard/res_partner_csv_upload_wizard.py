import json
import os

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..csv_source import FILES, load


class ResPartnerCsvUploadWizard(models.TransientModel):
    _name = 'res.partner.csv.upload.wizard'
    _description = 'Subir CSV de importación de partners'

    # ir.attachment + many2many_binary uploads over a dedicated multipart
    # route, not embedded as base64 in the record's own save() payload:
    # a plain fields.Binary breaks on files this large (~150MB).
    attachment_ids = fields.Many2many('ir.attachment', string='Archivos CSV')
    target_dir = fields.Char(readonly=True)
    summary = fields.Text(readonly=True)

    def action_upload(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise UserError(_('Administrator required'))
        by_name = {att.name: att for att in self.attachment_ids}
        missing = [name for name in FILES if name not in by_name]
        if missing:
            raise UserError(_('Missing file(s), rename to match exactly: %s') % ', '.join(missing))
        target_dir = self.env['res.partner.csv.import.run']._csv_dir()
        for filename in FILES:
            with open(os.path.join(target_dir, filename), 'wb') as stream:
                stream.write(by_name[filename].raw)
        # Structural preflight only: no database writes, confirms the files
        # just written are readable and well-formed before anyone runs the
        # real import from a shell.
        _rows, summary = load(target_dir)
        self.write(dict(target_dir=target_dir,
                        summary=json.dumps(summary, ensure_ascii=False, indent=2)))
        return dict(type='ir.actions.act_window', res_model=self._name, res_id=self.id,
                   view_mode='form', target='new')
