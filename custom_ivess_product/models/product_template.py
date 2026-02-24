from odoo import models, fields, _, api
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('repairable', 'Repairable'),
        ],
        string='Status',
        required=True,
        copy=False,
        tracking=True,
        default='new',
    )

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
        categ = self.env['product.category'].browse(categ_id) if categ_id else False
        if not categ:
            raise ValidationError(_("Product category is required to generate the reference."))
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
