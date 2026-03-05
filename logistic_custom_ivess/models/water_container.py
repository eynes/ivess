from odoo import models, fields, api


class WaterContainer(models.Model):
    _name = 'water.container'
    _description = 'Water Container'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Container Number', 
        required=True, 
        copy=False, 
        readonly=True, 
        default='Nuevo'
    )
    partner_id = fields.Many2one(
        'res.partner', 
        string='Customer', 
        invisible=True
    )
    container_type = fields.Selection(
        [
            ('bottle', 'Bottle'),
            ('jug', 'Jug'),
        ], 
        string='Container Type', 
        required=True
    )
    assignment_date = fields.Date(
        string='Assignment Date', 
        required=True
    )
    return_date = fields.Date(
        string='Return Date'
    )
    state_id = fields.Many2one(
        'water.container.state', 
        string='Status', 
        required=True, 
        tracking=True
    )

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if not vals.get('name') or vals['name'] in ('/', 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.water.container') or '/'

        records = super().create(vals_list)
        return records


class WaterContainerState(models.Model):
    _name = 'water.container.state'
    _description = 'Water Container Status'
    _order = 'code'

    name = fields.Char(string='Status', required=True)
    code = fields.Integer(
        string='Code',
        readonly=True,
        copy=False,
        index=True
    )
    is_pending_return = fields.Boolean(string="Pending return")

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        # Obtener el último código actual
        last_code = self.search([], order='code desc', limit=1).code or 0

        for vals in vals_list:
            last_code += 1
            vals['code'] = last_code

        return super(WaterContainerState, self).create(vals_list)