from odoo import fields, models


class PartnerDistributionSugerencia(models.TransientModel):
    """Opción de reparto + día cercana al cliente. Son registros virtuales:
    se arman al abrir la distribución y no se guardan."""

    _name = 'partner.distribution.sugerencia'
    _description = 'Opción de reparto y día más cercana'

    distribution_parent_id = fields.Many2one('partner.distribution', ondelete='cascade')
    plantilla_id = fields.Many2one('template.delivery.route', string='Plantilla', readonly=True)
    name = fields.Char(string='Reparto y día', readonly=True)
    distancia = fields.Float(string='Distancia (km)', digits=(16, 1), readonly=True)
    franja = fields.Char(
        string='Franja habitual',
        readonly=True,
        help='Hora promedio de visita de los clientes cercanos de esta plantilla.',
    )
    usar = fields.Boolean(string='Usar')
