from odoo import models, fields, api, tools

class IvessDeliveryAndAssignedRouteReport(models.Model):
    _name = "ivess.delivery.and.assigned.route.report"
    _description = "Vista SQL de reparto + rutas asignadas expuesta al middleware Ivess"
    _auto = False

    # delivery.route
    delivery_date = fields.Date(readonly=True)
    state_dr = fields.Selection(
        selection=lambda self: self.env['delivery.route']._fields['state'].selection,
        readonly=True,
    )
    template_delivery_route_id = fields.Many2one('template.delivery.route', readonly=True)

    #delivery.route.number
    allow_price_editing = fields.Boolean(readonly=True)
    allow_free_of_charge = fields.Boolean(readonly=True)
    is_cold_hot_delivery = fields.Boolean(readonly=True)
    number = fields.Integer(readonly=True)
    allow_cash_sale = fields.Boolean(readonly=True)
    allow_manual_address = fields.Boolean(readonly=True)
    allow_previous_price = fields.Boolean(readonly=True)
    date_from_drn = fields.Date(readonly=True)
    date_to_drn = fields.Date(readonly=True)
    allow_sale_without_stock = fields.Boolean(readonly=True)
    allow_reordering = fields.Boolean(readonly=True)

    #res.partner
    state_rp = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['state'].selection,
        readonly=True,
    )
    date_from_rp = fields.Date(readonly=True)
    date_to_rp = fields.Date(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW ivess_delivery_and_assigned_route_report AS (
                SELECT
                    drl.id AS id,
                    dr.delivery_date AS delivery_date,
                    dr.state AS state_dr,
                    dr.template_delivery_route_id AS template_delivery_route_id,
                    drn.allow_price_editing AS allow_price_editing,
                    drn.allow_free_of_charge AS allow_free_of_charge,
                    drn.is_cold_hot_delivery AS is_cold_hot_delivery,
                    drn.number AS number,
                    drn.allow_cash_sale AS allow_cash_sale,
                    drn.allow_manual_address AS allow_manual_address,
                    drn.allow_previous_price AS allow_previous_price,
                    drn.date_from AS date_from_drn,
                    drn.date_to AS date_to_drn,
                    drn.allow_sale_without_stock AS allow_sale_without_stock,
                    drn.allow_reordering AS allow_reordering,
                    rp.state AS state_rp,
                    rp.date_from AS date_from_rp,
                    rp.date_to AS date_to_rp
                FROM delivery_route dr
                JOIN delivery_route_line drl ON drl.route_id = dr.id
                JOIN res_partner rp ON rp.id = drl.client_id
                JOIN delivery_route_number drn ON drn.id = dr.delivery_number_id
            )
        """.format(table=self._table))
    
    @api.model
    def get_delivery_and_assigned_route_report(self, **kwargs):
        allowed_params = {"distribution"}
        unknown_params = set(kwargs) - allowed_params
        if unknown_params:
            return {
                "error": "Parámetros no reconocidos: %s. "
                        "Los parámetros aceptados son: distribution."
                        % ", ".join(sorted(unknown_params))
            }
        distribution = kwargs.get("distribution")
        if not distribution:
            return {
                "error": "Se requiere el parámetro distribution."
            }
        if not isinstance(distribution, str):
            return {
                "error": "El parámetro 'distribution' debe ser una cadena de texto. "
                        "Tipo recibido: %s." % type(distribution).__name__
            }

        template = self.env['template.delivery.route'].search([('name', '=', distribution)], limit=1)
        if not template:
            return {"error": "No existe una distribución con el código '%s'." % distribution}

        records = self.search([('template_delivery_route_id', '=', template.id)])
        if not records:
            return {"error": "No hay rutas/clientes asignados para la distribución '%s'." % distribution}

        fields_to_read = [
            'delivery_date', 
            'state_dr', 
            'template_delivery_route_id',
            'allow_price_editing', 
            'allow_free_of_charge', 
            'is_cold_hot_delivery',
            'number', 
            'allow_cash_sale', 
            'allow_manual_address', 
            'allow_previous_price',
            'date_from_drn', 
            'date_to_drn', 
            'allow_sale_without_stock', 
            'allow_reordering',
            'state_rp', 
            'date_from_rp', 
            'date_to_rp',
        ]
        return {"result": records.read(fields_to_read)}

