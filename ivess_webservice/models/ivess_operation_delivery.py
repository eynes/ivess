from dataclasses import dataclass

from odoo import Command, api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from datetime import datetime
import pytz

from ..utils.delivery_params import (
    BASIC_HEADER_SCHEMA,
    CONTAINER_STATE_BY_TIPO_VENTA,
    SALE_SCHEMA,
    requires_container_state,
    validate_case_params,
    validate_header,
    validate_series,
    validate_tipo_venta,
)

APP_DATETIME_FORMAT = "%Y-%m-%d %H%M"
APP_TIMEZONE = "America/Argentina/Buenos_Aires"


@dataclass
class SaleOutcome:
    """Resultado de procesar la venta: registros creados y errores no fatales."""
    order: models.BaseModel
    picking: models.BaseModel
    confirm_error: str | bool = False
    validate_error: str | bool = False


class IvessOperationDelivery(models.AbstractModel):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        """Registra la visita de un reparto, con o sin venta.

        Fases: validar parametros -> resolver registros (ubicacion, reparto,
        cliente, recorrido, linea) -> validar la venta contra productos y series
        -> crear y confirmar la venta -> preparar y validar el picking ->
        escribir la linea del recorrido -> responder.

        Todas las validaciones van antes de cualquier escritura: un return de
        error no hace rollback.
        """
        # La app puede no lograr calcular los metros y enviarlos como null
        if "metros" in kwargs and ((kwargs["metros"] is None) or (kwargs["metros"] == 0)):
            kwargs["metros"] = -1

        # Fase 1: cabecera basica. Va primero porque motivo_no_compra
        # define el caso y, por ende, que otros parametros se esperan.
        error = validate_header(kwargs).message()
        if error:
            return {"error": error}

        case_schema = {}
        if kwargs["motivo_no_compra"] == 0:
            case_schema.update(SALE_SCHEMA)
        expected_params_types = {**BASIC_HEADER_SCHEMA, **case_schema}

        unknown_params = set(kwargs) - set(expected_params_types)
        if unknown_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        # Fase 2: parametros propios del caso
        error = validate_case_params(kwargs, case_schema).message()
        if error:
            return {"error": error}

        usuario_reparto = kwargs["usuario_reparto"]
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
        item_venta = kwargs.get("item_venta", [])

        try:
            visit_date_hour = self._app_datetime_to_utc(fecha_operacion, hora_atencion)
            phone_date_hour = self._app_datetime_to_utc(fecha_operacion, hora_envio)
        except ValueError:
            return {"error" : "Formato invalido: fecha_operacion debe ser YYYY-MM-DD y hora_atencion, hora_envio HHMM."}

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
        if not motivo_no_compra and motivo_no_compra_id != 0:
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
        if fuera_ruta and linea:
            return {"error": "El cliente %s ya tiene linea en el recorrido; no puede enviarse como fuera de ruta." % codigo_cliente}
        if not fuera_ruta and not linea:
            return {"error": "El cliente %s no pertenece al recorrido del reparto %s." % (codigo_cliente, aguas_idreparto)}

        products_by_code = {}
        duplicated_codes = {}
        if item_venta:
            if linea.sale_order_id:
                return {"error": "El cliente %s ya tiene una venta registrada en el recorrido (%s)." % (codigo_cliente, linea.sale_order_id.name)}

            if not ubicacion.warehouse_id:
                return {"error": "La ubicacion del reparto %s no pertenece a ningun almacen." % aguas_idreparto}

            codes = {item["codigo_producto"] for item in item_venta}
            products = self.env["product.product"].search([
                ("default_code", "in", list(codes)),
                ("product_tmpl_id.show_in_app", "=", True),
                ("sale_ok", "=", True),
            ], order="id")
            for product in products:
                # default_code duplicado: se toma el mas antiguo y se avisa en la orden.
                code = product.default_code
                if code not in products_by_code:
                    products_by_code[code] = product
                else:
                    duplicated_codes.setdefault(code, [products_by_code[code]]).append(product)

            missing_codes = codes - set(products_by_code)
            if missing_codes:
                return {"error": "No existen productos con los codigos: %s" % ", ".join(sorted(missing_codes))}

            error = validate_tipo_venta(item_venta, products_by_code).message()
            if error:
                return {"error": error}

            series_errors, requested_series = validate_series(item_venta, products_by_code)
            error = series_errors.message()
            if error:
                return {"error": error}

            # REPASAR
            # Los pickings de salida no crean series: deben existir.
            lot_by_key = {}
            if requested_series:
                lots = self.env["stock.lot"].search(Domain.OR(
                    Domain([("product_id", "=", product_id), ("name", "=", serie)])
                    for product_id, serie in requested_series
                ), order="id desc")
                lot_by_key = {(lot.product_id.id, lot.name): lot for lot in lots}
                unknown_series = sorted(
                    "%s (%s)" % (serie, self.env["product.product"].browse(product_id).default_code)
                    for product_id, serie in requested_series - set(lot_by_key)
                )
                if unknown_series:
                    return {"error": "No existen numeros de serie: %s" % ", ".join(unknown_series)}

        vals = {
            "no_purchase_reason_id": motivo_no_compra.id,
            "visit_date_hour": visit_date_hour,
            "delivery_date_hour": phone_date_hour,
            "longitude": longitud,
            "latitude": latitud,
            "meters": str(metros),
            "app_user": usuario_reparto,
        }

        outcome = SaleOutcome(self.env["sale.order"], self.env["stock.picking"])
        if item_venta:
            outcome = self._process_sale(
                cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes,
            )
            vals["sale_order_id"] = outcome.order.id
            if outcome.picking:
                vals["stock_picking_id"] = outcome.picking.id

        if fuera_ruta:
            linea = self.env["delivery.route.line"].create({
                **vals,
                "route_id": recorrido.id,
                "client_id": cliente.id,
            })
        else:
            linea.write(vals)

        return self._build_response(linea, outcome)

    def _process_sale(self, cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes):
        """Crea la venta, la confirma y prepara y valida su picking.
        Confirmar y validar son best effort: la venta ya ocurrio, asi que si
        fallan se registra el error y se sigue."""
        order = self._create_sale_order(
            cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes,
        )
        outcome = SaleOutcome(order, self.env["stock.picking"])
        outcome.confirm_error = self._confirm_sale_order(order)
        # Sin confirmacion, o con una orden solo de servicios, no hay picking.
        outcome.picking = order.picking_ids[:1]
        if outcome.picking:
            outcome.validate_error = (
                self._prepare_picking(outcome.picking, reparto)
                or self._validate_picking(outcome.picking)
            )
            if outcome.validate_error:
                outcome.picking.message_post(
                    body="La validacion automatica desde la app fallo y el picking quedo sin validar: %s" % outcome.validate_error
                )
        return outcome

    def _create_sale_order(self, cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes):
        # El precio de la app es absoluto: discount en 0 evita que
        # pricelist_custom aplique el descuento del cliente encima.
        order_lines = []
        for item in item_venta:
            product = products_by_code[item["codigo_producto"]]
            container_state = False
            if requires_container_state(product):
                container_state = CONTAINER_STATE_BY_TIPO_VENTA[item["tipo_venta"]]
            order_lines.append(Command.create({
                "product_id": product.id,
                "product_uom_qty": item["cantidad"],
                "price_unit": item["precio_venta"],
                "discount": 0.0,
                "container_state": container_state,
                "serial_lot_ids": [Command.set([lot_by_key[(product.id, serie)].id for serie in item.get("series") or []])],
            }))
        order = self.env["sale.order"].create({
            "partner_id": cliente.id,
            "warehouse_id": reparto.location_id.warehouse_id.id,
            "delivery_route_id": recorrido.id,
            "order_line": order_lines,
        })
        if duplicated_codes:
            order.message_post(body="#REVISAR Codigos de producto repetidos: se tomo el producto mas antiguo. %s" % "; ".join(
                "%s: tomado id %s, descartados ids %s" % (
                    code, candidates[0].id, ", ".join(str(p.id) for p in candidates[1:]),
                ) for code, candidates in sorted(duplicated_codes.items())
            ))
        return order

    def _confirm_sale_order(self, order):
        """Si la confirmacion falla (casi siempre por configuracion de Odoo,
        no por los datos enviados) se deshace solo ella y la orden queda en
        borrador. Devuelve el error o False."""
        try:
            with self.env.cr.savepoint():
                order.action_confirm()
        except UserError as e:
            order.message_post(
                body="La confirmacion automatica desde la app fallo y la orden quedo en borrador: %s" % e
            )
            return str(e)
        return False

    def _prepare_picking(self, picking, reparto):
        """Pasa el picking a la ubicacion del camion. Devuelve el error si falta
        stock y el reparto no permite vender sin stock; si lo permite, fuerza la
        cantidad vendida. Va fuera de savepoint: son datos de la request y deben
        persistir aunque la validacion falle."""
        # La confirmacion reservo en el almacen: se libera y se reserva de nuevo.
        # write() del picking propaga la ubicacion a sus moves.
        picking.do_unreserve()
        picking.write({"location_id": reparto.location_id.id})
        picking.action_assign()
        shortage = picking.move_ids.filtered(lambda m: m.state != "assigned")
        if not shortage:
            return False
        if not reparto.allow_sale_without_stock:
            return "Stock insuficiente en la ubicacion del reparto para completar el picking %s." % picking.name
        picking.message_post(body="Stock insuficiente en la ubicacion del reparto: se forzo la cantidad vendida. %s" % "; ".join(
            "%s: reservado %s de %s" % (move.product_id.display_name, move.quantity, move.product_uom_qty)
            for move in shortage
        ))
        for move in shortage:
            # Con serie se fuerza cada unidad con su serie: una linea sin serie
            # no pasa el _sanity_check del picking.
            if move.has_tracking == "serial" and move.sale_line_id.serial_lot_ids:
                move.lot_ids = move.sale_line_id.serial_lot_ids
            else:
                move.quantity = move.product_uom_qty
        return False

    def _validate_picking(self, picking):
        """Si la validacion falla se deshace solo ella: el picking queda sin
        validar y vinculado. Devuelve el error o False."""
        try:
            with self.env.cr.savepoint():
                # skip_backorder: sin esto button_validate devuelve el wizard de
                # backorder. Puede devolver acciones de impresion, por eso el
                # exito se verifica por el estado.
                picking.with_context(
                    skip_backorder=True,
                    picking_ids_not_to_backorder=picking.ids,
                ).button_validate()
                if picking.state != "done":
                    raise UserError("No se pudo validar el picking %s (estado: %s)." % (picking.name, picking.state))
        except UserError as e:
            return str(e)
        return False

    def _build_response(self, linea, outcome):
        result = {"success": True, "route_line_id": linea.id}
        if outcome.order:
            result["sale_order_id"] = outcome.order.id
            result["sale_order_confirmed"] = not outcome.confirm_error
            result["picking_validated"] = outcome.picking.state == "done"
            # Son excluyentes: sin confirmacion no hay picking que validar
            if outcome.confirm_error:
                result["warning"] = "No se pudo confirmar la venta: %s" % outcome.confirm_error
            elif outcome.validate_error:
                result["warning"] = "No se pudo validar el picking: %s" % outcome.validate_error
        return result

    def _app_datetime_to_utc(self, fecha, hora):
        """Convierte fecha YYYY-MM-DD + hora HHMM (hora de Argentina) a UTC naive.
        Lanza ValueError si el formato es invalido."""
        local = datetime.strptime(fecha + " " + hora, APP_DATETIME_FORMAT)
        tz = pytz.timezone(APP_TIMEZONE)
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
