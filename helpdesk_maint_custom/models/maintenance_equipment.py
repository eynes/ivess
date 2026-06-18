# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    is_vehicle = fields.Boolean(string="Es vehículo")
    supply_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación de insumos',
    )
    infraction_ids = fields.One2many(
        'maintenance.equipment.infraction',
        'equipment_id',
        string='Infracciones',
    )


class MaintenanceEquipmentInfraction(models.Model):
    _name = 'maintenance.equipment.infraction'
    _description = 'Infracción de equipo/vehículo'

    equipment_id = fields.Many2one(
        'maintenance.equipment',
        required=True,
        ondelete='cascade',
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Conductor/Legajo',
    )
    photo = fields.Image(string='Foto', max_width=256, max_height=256)
    amount = fields.Float(string='Monto', digits=(10, 2))
    infraction_date = fields.Date(string='Fecha de infracción')
    infraction_reason = fields.Char(string='Motivo de infracción')
    infraction_location = fields.Char(string='Lugar de infracción')
    internal_note = fields.Text(string='Nota interna')
