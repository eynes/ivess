from odoo import models, fields, _, api
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    abbreviation = fields.Char(
        string='Abbreviation',
        size=10,
        help=_('Short reference name (max 10 characters)'),
    )
    order = fields.Integer(string="Order")
    is_returnable = fields.Boolean(
        string="Is returnable",
        required=True,
        default=False,
        tracking=True,
    )
    is_frio_calor = fields.Boolean(
        string="Es Frio/Calor",
        default=False,
        tracking=True,
    )
    litros_min_bonificacion = fields.Integer(
        string="Litros mínimos para bonificación"
    )
    allows_replacement = fields.Boolean(string="Allows Replacement")
    exclude_from_regular = fields.Boolean(string="Exclude from Regular")
    show_in_app = fields.Boolean(string="Mostrar en App")
    is_promo = fields.Boolean(string="Is Promo")

    _sql_constraints = [
        (
            'unique_abbreviation',
            'unique(abbreviation)',
            _('Duplicate abbreviation.')
        )
    ]

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('repairable', 'Repairable'),
        ],
        string='Status',
        copy=False,
        tracking=True,
        default='new',
    )

    @api.constrains('purchase_ok', 'categ_id', 'state')
    def _check_purchase_required_fields(self):
        for rec in self:
            if not rec.purchase_ok:
                continue
            if not rec.categ_id:
                raise ValidationError(
                    _("Product Category is required for purchase products.")
                )
            if not rec.state:
                raise ValidationError(
                    _("Status is required for purchase products.")
                )

    @api.constrains('abbreviation')
    def _check_abbreviation(self):
        for rec in self:
            if rec.abbreviation:
                if len(rec.abbreviation) > 10:
                    raise ValidationError(_("The abbreviation cannot exceed 10 characters."))
                duplicate = self.search([
                    ('abbreviation', '=', rec.abbreviation),
                    ('id', '!=', rec.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("Duplicate abbreviation."))

    def create(self, vals):
        """
        Generates the internal reference (default_code) during product creation
        based on the product's state and category.
        Args:
            vals (list): list of dict of field values for the new product.
        Returns:
            recordset: The newly created product record.
        """
        if isinstance(vals, dict):
            vals = [vals]
        for val in vals:
            state = val.get(
                'state',
                self._fields['state'].default(self)
            )
            categ_id = val.get('categ_id', False)
            val.update({'default_code': self._generate_default_code(state, categ_id)})
        return super(ProductTemplate, self).create(vals)

    def write(self, vals):
        """
        Updates the internal reference (default_code) if the product's state
        or category is changed.
        Args:
            vals (dict): Dictionary of updated field values for the product.
        Returns:
            bool: True if the write operation was successful.
        """
        for rec in self:
            new_vals = dict(vals)
            if rec.has_change_state(vals) or rec.has_change_categ(vals):
                state = vals.get('state', rec.state)
                categ_id = vals.get('categ_id', rec.categ_id.id)
                default_code = self._generate_default_code(state, categ_id)
                # Se actualiza aunque sea False / vacío
                new_vals['default_code'] = default_code
        super(ProductTemplate, rec).write(new_vals)
        return True

    def has_change_state(self, vals):
        return 'state' in vals and vals['state'] != self.state

    def has_change_categ(self, vals):
        return 'categ_id' in vals and vals['categ_id'] != self.categ_id.id

    def _generate_default_code(self, state, categ_id):
        """
        Helper function to generate the internal reference (default_code)
        based on the product's state and category.
        Args:
            state (str): The product's state ('new' or 'repairable').
            categ_id (int): The ID of the product's category.
        Returns:
            str: The generated default_code based on the category's sequence, or an empty string if no sequence is available.
        """
        if not categ_id:
            return False
        categ = self.env['product.category'].browse(categ_id)
        if state == 'new':
            if not categ.new_sequence_id:
                raise ValidationError(
                    _("Category %s does not have a New sequence configured.") % categ.name
                )
            return categ.new_sequence_id.next_by_id()
        if state == 'repairable':
            if not categ.repaired_sequence_id:
                raise ValidationError(
                    _("Category %s does not have a Repair sequence configured.") % categ.name
                )
            return categ.repaired_sequence_id.next_by_id()
