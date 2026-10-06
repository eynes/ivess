from odoo import fields, api, models
from datetime import datetime
import pytz

class IvessOperationDelivery(models.AbstractModel):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        expected_params_types = {
            "usuario_reparto": str,
            "fecha_operacion": str,
            "nro_reparto": int,
            "hora_atencion": str,
            "hora_envio": str,
            "codigo_cliente": str,
            "motivo_no_compra": int,
            "longitud": str,
            "latitud": str,
            "metros": int, #revisar
            "fuera_ruta": bool,
        }

        unknown_params = set(kwargs) - set(expected_params_types)

        if unknown_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        missing_params = []
        for param in sorted(expected_params_types):
            value = kwargs.get(param)
            if value is None or value == "":
                missing_params.append(param)

        if missing_params:
            return {"error" : "Faltan parametros obligatorios: %s" % ", ".join(missing_params)}

        invalid_types = []
        for param, expected_type in expected_params_types.items():
            if type(kwargs[param]) is not expected_type:
                invalid_types.append("%s (%s)" % (param, expected_type.__name__))

        if invalid_types:
            return {"error" : "Tipo invalido en parametros: %s" % ", ".join(invalid_types)}

        fecha_operacion = kwargs["fecha_operacion"]
        aguas_idreparto = kwargs["nro_reparto"]
        hora_atencion = kwargs["hora_atencion"]
        hora_envio = kwargs["hora_envio"]
        codigo_cliente = kwargs["codigo_cliente"]
        motivo_no_compra_id = kwargs["motivo_no_compra"]
        longitud = kwargs["longitud"]
        latitud = kwargs["latitud"]
        metros = kwargs["metros"]
        fuera_ruta = kwargs["fuera_ruta"]

        fdt = "%Y-%m-%d %H%M"
        try:
            visit_date_hour = datetime.strptime(fecha_operacion + " " + hora_atencion, fdt)
            phone_date_hour = datetime.strptime(fecha_operacion + " " + hora_envio, fdt)
        except ValueError:
            return {"error" : "Formato invalido: fecha_operacion debe ser YYYY-MM-DD y hora_atencion, hora_envio HHMM."}

        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        visit_date_hour = tz.localize(visit_date_hour).astimezone(pytz.utc).replace(tzinfo=None)
        phone_date_hour = tz.localize(phone_date_hour).astimezone(pytz.utc).replace(tzinfo=None)

        ubicacion = self.env["stock.location"].search([("aguas_idreparto", "=", aguas_idreparto)], limit=1)
        if not ubicacion:
            return {"error" : "No existe ubicacion asociada al nro de reparto provisto."}

        reparto = self.env["delivery.route.number"].search([("location_id", "=", ubicacion.id)], limit=1)
        if not reparto:
            return {"error" : "No existe reparto asociado a la ubicacion del nro de reparto provisto."}

        cliente = self.env["res.partner"].search([("customer_code", "=", codigo_cliente)], limit=1)
        if not cliente:
            return {"error": "No existe cliente con el codigo: %s" % codigo_cliente}

        motivo_no_compra = self.env["no.purchase.reason"].search([("id", "=", motivo_no_compra_id)], limit=1)
        if not motivo_no_compra:
            return {"error": "No existe motivo de no compra con id: %s" % motivo_no_compra_id}

        recorrido = self.env["delivery.route"].search([
            ("delivery_number_id", "=", reparto.id),
            ("delivery_date", "=", fecha_operacion),
            ("state", "=", "in_progress"),
        ], limit=1)
        if not recorrido:
            return {"error": "No existe recorrido en progreso para el reparto %s en la fecha %s" % (aguas_idreparto, fecha_operacion)}

        linea = self.env["delivery.route.line"].search([
            ("route_id", "=", recorrido.id),
            ("client_id", "=", cliente.id),
            ("origin", "!=", "rastrillo"),
        ], limit=1)

        vals = {
            "no_purchase_reason_id": motivo_no_compra.id,
            "visit_date_hour": visit_date_hour,
            "delivery_date_hour": phone_date_hour,
            "longitude": longitud,
            "latitude": latitud,
            "meters": str(metros),
        }

        if fuera_ruta:
            if linea:
                return {"error": "El cliente %s ya tiene linea en el recorrido; no puede enviarse como fuera de ruta." % codigo_cliente}
            linea = self.env["delivery.route.line"].create({
                **vals,
                "route_id": recorrido.id,
                "client_id": cliente.id,
            })
        else:
            if not linea:
                return {"error": "El cliente %s no pertenece al recorrido del reparto %s." % (codigo_cliente, aguas_idreparto)}
            linea.write(vals)

        return {"success": True, "route_line_id": linea.id}
