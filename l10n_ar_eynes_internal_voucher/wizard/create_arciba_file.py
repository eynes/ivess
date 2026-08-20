import logging

from odoo import _, models
from odoo.exceptions import ValidationError

logger = logging.getLogger(__name__)


class CreateArcibaFiles(models.TransientModel):
    _inherit = 'create.arciba.files'

    def create_files(self):
        """
        Entrypoint to exporter
        """
        errors = ''
        cr = self.env.cr
        # Buscamos las perception_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de percepcion

        perception_query = """
            SELECT p.id
            FROM perception_tax_line p
            JOIN account_move i ON p.invoice_id = i.id
            JOIN account_tax at ON p.perception_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND i.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'sale'  -- Only perceptions applied
            AND i.move_type IN ('out_invoice')  -- Not including refunds(NC)
            ORDER BY p.date """

        query_vals = {
            'period_start': self.period_start,
            'period_end': self.period_end,
            'state': 'posted',
            'company_id': self.company_id.id,
        }
        cr.execute(perception_query, query_vals)
        res = cr.fetchall()
        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 perception_tax_line, got %s' % len(res)
        except BaseException:
            perception_errors = False
            perception_vals = []
            logger.warning('No perceptions to export')
        else:
            perception_ids = [perception_ids[0] for perception_ids in res]

            # Excluir comprobantes internos (no se informan a ARCIBA)
            lines = self.env['perception.tax.line'].browse(perception_ids)
            lines = lines.filtered(
                lambda l: l.invoice_id.journal_id.fiscal_type
                != 'internal_voucher'
            )
            perception_ids = lines.ids

            if not perception_ids:
                perception_errors = False
                perception_vals = []
                logger.warning('No perceptions to export')
            else:
                perception_errors, perception_vals = self._get_perc_data(
                    perception_ids
                )

        if perception_errors:
            errors += _('Perception File Errors\n================\n')
            errors += '\n'.join(perception_vals)
            errors += '\n\n\n'

        # Buscamos las retention_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de retención

        retention_query = """
            SELECT p.id
            FROM account_payment_order_retention_line p
            JOIN account_payment_order op ON p.payment_order_id = op.id
            JOIN account_tax at ON p.retention_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND op.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'purchase'  -- Only retentions applied
            ORDER BY p.date
        """

        cr.execute(retention_query, query_vals)
        res = cr.fetchall()

        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 retention_tax_line, got %s' % len(res)
        except BaseException:
            retention_errors = False
            retention_vals = []
            logger.warning('No retentions to export')
        else:
            retention_ids = [retention_ids[0] for retention_ids in res]
            retention_errors, retention_vals = self._get_ret_data(retention_ids)

        if retention_errors:
            errors += _('Retention File Errors\n================\n')
            errors += '\n'.join(retention_vals)

        if errors:
            self.write({'notes': errors})
            form_res = self.env.ref('l10n_ar_eynes.view_create_arciba_files')
            form_id = form_res and form_res.id or False
            res = {
                'name': _('Arciba'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.arciba.files',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            data_lst = retention_vals + perception_vals
            data_lst_sorted = sorted(data_lst, key=lambda x: x['fecha'])
            if data_lst:
                res = self.generate_fw_file(data_lst_sorted)
            else:
                raise ValidationError(
                    _(
                        "No perceptions/retentions from %(start)s to %(end)s to inform eArciba.",
                        start=self.period_start,
                        end=self.period_end,
                    )
                )
        return res


class CreateArcibaNcFile(models.TransientModel):
    _inherit = 'create.arciba.nc.file'

    def create_files(self):
        """
        Entrypoint to exporter
        """
        errors = ''
        cr = self.env.cr

        # Buscamos las perception_tax_line del periodo pedido
        # ordenados segun lo escrito en documento tecnico agip
        # El archivo de importación debe estar ordenado por fecha de percepcion

        perception_query = """
            SELECT p.id
            FROM perception_tax_line p
            JOIN account_move i ON p.invoice_id = i.id
            JOIN account_tax at ON p.perception_id = at.id
            WHERE p.date BETWEEN %(period_start)s AND %(period_end)s
            AND p.company_id = %(company_id)s
            AND i.state = %(state)s
            AND at.inform_arciba=True
            AND at.type_tax_use LIKE 'sale'  -- Only perceptions applied
            AND i.move_type IN ('out_refund')  -- Only including refunds(NC)
            ORDER BY p.date """

        query_vals = {
            'period_start': self.period_start,
            'period_end': self.period_end,
            'state': 'posted',
            'company_id': self.company_id.id,
        }

        cr.execute(perception_query, query_vals)
        res = cr.fetchall()
        try:
            assert (
                len(res) > 0
            ), 'Expected at least 1 perception_tax_line, got %s' % len(res)
        except BaseException:
            perception_errors = False
            perception_vals = []
            logger.warning('No perceptions to export')
        else:
            inv_ids = [inv_id[0] for inv_id in res]  # Fixed list

            # Excluir comprobantes internos (no se informan a ARCIBA)
            lines = self.env['perception.tax.line'].browse(inv_ids)
            lines = lines.filtered(
                lambda l: l.invoice_id.journal_id.fiscal_type
                != 'internal_voucher'
            )
            inv_ids = lines.ids

            if not inv_ids:
                perception_errors = False
                perception_vals = []
                logger.warning('No perceptions to export')
            else:
                perception_errors, perception_vals = self._get_inv_data(
                    inv_ids
                )

        if perception_errors:
            errors += _('Perception File Errors\n================\n')
            errors += '\n'.join(perception_vals)
            errors += '\n\n\n'

        if errors:
            self.write({'notes': errors})
            form_res = self.env.ref('l10n_ar_eynes.view_create_arciba_nc_file')
            form_id = form_res and form_res.id or False
            res = {
                'name': _('Arciba'),
                'view_type': 'form',
                'view_mode': 'form',
                'views': [
                    (form_id, 'form'),
                ],
                'res_model': 'create.arciba.nc.file',
                'res_id': self.id,
                'view_id': form_id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        else:
            if perception_vals:
                res = self.generate_fw_file(perception_vals)
            else:
                raise ValidationError(
                    _(
                        "No perceptions/retentions from %(start)s to %(end)s to inform eArciba.",
                        start=self.period_start,
                        end=self.period_end,
                    )
                )
        return res
