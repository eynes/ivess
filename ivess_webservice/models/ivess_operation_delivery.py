from odoo import fields, api, models
from datetime import datetime
import pytz

class IvessOperationDelivery(models.Model):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        allowed_params = {
            "fecha_operacion",
            "nro_reparto",
            "hora_atencion",
            "hora_envio",
            "codigo_cliente",
            "motivo_no_compra",
            "longitud",
            "latitud",
            "metros",
            "fuera_ruta",
        }

        unknown_params = set(kwargs) - allowed_params

        if unknown_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        missing_params = []
        for param in sorted(allowed_params):
            value = kwargs.get(param)
            if value is None or value == "":
                missing_params.append(param)

        if missing_params:
            return {"error" : "Faltan parametros obligatorios: %s" % ", ".join(missing_params)}

        fecha_operacion = kwargs["fecha_operacion"]
        aguas_idreparto = kwargs["nro_reparto"]
        hora_atencion = kwargs["hora_atencion"]
        hora_envio = kwargs["hora_envio"]
        codigo_cliente = kwargs["codigo_cliente"]
        motivo_no_compra = kwargs["motivo_no_compra"]
        longitud = kwargs["longitud"]
        latitud = kwargs["latitud"]
        metros = kwargs["metros"]
        fuera_ruta = kwargs["fuera_ruta"]

        sdt = fecha_operacion + " " + hora_atencion
        fdt = "%Y-%m-%d %H%M"
        try:
            visit_date_hour = datetime.strptime(sdt, fdt)
        except Exception:
            return {"error" : "Formato invalido: fecha_operacion debe ser YYYY-MM-DD y hora_atencion HHMM."}

        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        visit_date_hour = tz.localize(visit_date_hour).astimezone(pytz.utc).replace(tzinfo=None)

        ubicacion = self.env["stock.location"].search([("aguas_idreparto", "=", aguas_idreparto)], limit=1)
        if not ubicacion:
            return {"error" : "No existe ubicacion asociada al nro de reparto provisto."}

        reparto = self.env["delivery.route.number"].search([("location_id", "=", ubicacion.id)], limit=1)
        if not reparto:
            return {"error" : "No existe reparto asociado a la ubicacion del nro de reparto provisto."}

        cliente = self.env["res.partner"].search([("customer_code", "=", codigo_cliente)], limit=1)
        if not cliente:
            return {"error": "No existe cliente con el codigo: %s" % codigo_cliente}




