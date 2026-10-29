from dataclasses import dataclass

from odoo import Command, api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from datetime import datetime
import pytz

from ..utils.delivery_params import (
    BASIC_HEADER_SCHEMA,
    CONTAINER_STATE,
    WITHDRAWAL_ITEMS,
    WithdrawalAvailability,
    case_param_names,
    requires_container_state,
    validate_case_params,
    validate_header,
    validate_series,
    validate_tipo,
    validate_withdrawal_availability,
)

APP_DATETIME_FORMAT = "%Y-%m-%d %H%M"
APP_TIMEZONE = "America/Argentina/Buenos_Aires"

# Origen de las lineas que crea el servicio. Un cliente tiene como maximo dos lineas
# por recorrido (sin contar rastrillo): la visita y una revisita.
ROUTE_LINE_ORIGIN_OUT_OF_ROUTE = "app_fuera_ruta"
ROUTE_LINE_ORIGIN_REVISIT = "app_revisita"
ROUTE_LINE_VISIT_FIELDS = (
    "visit_date_hour",
    "no_purchase_reason_id",
    "sale_order_id",
    "stock_picking_id",
    "withdrawal_picking_id",
)


@dataclass
class SaleOutcome:
    """Resultado de procesar la venta: registros creados y errores no fatales."""
    order: models.BaseModel
    picking: models.BaseModel
    confirm_error: str | bool = False
    validate_error: str | bool = False


@dataclass
class WithdrawalOutcome:
    """Resultado del retiro de envases: picking y errores no fatales.
    Sin picking y con create_error, no se llego a crear. Con picking y
    confirm_error, quedo en borrador."""
    picking: models.BaseModel
    create_error: str | bool = False
    confirm_error: str | bool = False
    validate_error: str | bool = False


class IvessOperationDelivery(models.AbstractModel):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        """Registra la visita de un reparto: con venta, con motivo de no compra
        o con retiro de envases (solo o combinado).

        Fases: validar parametros -> resolver registros (ubicacion, reparto,
        cliente, recorrido) y la linea de la visita (un reintento responde sin
        escribir) -> validar la venta y el retiro contra productos, series y
        envases del cliente -> crear y confirmar la venta, preparar y validar su
        picking -> crear y validar el picking de retiro -> escribir o crear la
        linea del recorrido -> responder.

        Todas las validaciones van antes de cualquier escritura: un return de
        error no hace rollback.
        """
        # La app puede no lograr calcular los metros y enviarlos como null
        if "metros" in kwargs and ((kwargs["metros"] is None) or (kwargs["metros"] == 0)):
            kwargs["metros"] = -1

        # Fase 1: cabecera basica y parametros desconocidos
        error = validate_header(kwargs).message()
        if error:
            return {"error": error}

        unknown_params = set(kwargs) - set(BASIC_HEADER_SCHEMA) - case_param_names(kwargs)
        if unknown_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        # Fase 2: parametros propios del caso 
        error = validate_case_params(kwargs).message()
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
        item_venta = kwargs.get("item_venta") or []
        item_retiro = kwargs.get("item_retiro") or []

        # Fase 3: resolver registros (ubicacion, reparto, cliente, motivo,
        # recorrido) y la linea de la visita. Un reintento responde sin escribir.
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

        retry_line, linea, error = self._resolve_route_line(recorrido, cliente, fuera_ruta, visit_date_hour)
        if error:
            return {"error": error}
        if retry_line:
            # Reintento de una visita ya registrada: no se escribe nada.
            return self._build_retry_response(retry_line)

        # Fase 4: validar venta y retiro contra la base (productos, series y
        # envases del cliente). Solo lee: un error se devuelve sin escribir.
        if (item_venta or item_retiro) and not ubicacion.warehouse_id:
            return {"error": "La ubicacion del reparto %s no pertenece a ningun almacen." % aguas_idreparto}

        products_by_code = {}
        duplicated_codes = {}
        if item_venta:
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

            error = validate_tipo(item_venta, products_by_code).message()
            if error:
                return {"error": error}

            series_errors, requested_series = validate_series(item_venta, products_by_code)
            error = series_errors.message()
            if error:
                return {"error": error}

            lot_by_key = {}
            if requested_series:
                lots = self.env["stock.lot"].search(Domain.OR(
                    [("product_id", "=", product_id), ("name", "=", serie)]
                    for product_id, serie in requested_series
                ), order="id desc")
                lot_by_key = {(lot.product_id.id, lot.name): lot for lot in lots}
                missing_series = requested_series - set(lot_by_key)
                if missing_series:
                    code_by_product_id = {product.id: code for code, product in products_by_code.items()}
                    unknown_series = sorted(
                        "%s (%s)" % (serie, code_by_product_id[product_id])
                        for product_id, serie in missing_series
                    )
                    return {"error": "No existen numeros de serie: %s" % ", ".join(unknown_series)}

        withdrawal_products = {}
        withdrawal_lots = {}
        if item_retiro:
            codes = {item[WITHDRAWAL_ITEMS.code] for item in item_retiro}
            withdrawal_products = self._withdrawal_products(codes, cliente)
            missing_codes = codes - set(withdrawal_products)
            if missing_codes:
                return {"error": "No existen productos de retiro con los codigos: %s" % ", ".join(sorted(missing_codes))}

            error = validate_tipo(item_retiro, withdrawal_products, WITHDRAWAL_ITEMS).message()
            if error:
                return {"error": error}

            error = validate_series(item_retiro, withdrawal_products, WITHDRAWAL_ITEMS)[0].message()
            if error:
                return {"error": error}

            products_to_withdraw = self.env["product.product"].union(*withdrawal_products.values()) # recordset de productos a retirar
            availability = self._withdrawal_availability(cliente, products_to_withdraw)
            error = validate_withdrawal_availability(item_retiro, withdrawal_products, availability).message()
            if error:
                return {"error": error}
            withdrawal_lots = availability.lots

        # Fase 5: escribir. Desde aca los fallos ya no cortan el flujo: se
        # informan como warning. Venta, retiro y despues la linea del recorrido.
        vals = {
            "no_purchase_reason_id": motivo_no_compra.id,
            "visit_date_hour": visit_date_hour,
            "delivery_date_hour": phone_date_hour,
            "longitude": longitud,
            "latitude": latitud,
            "meters": str(metros),
            "app_user": usuario_reparto,
        }

        outcome = SaleOutcome(self.env["sale.order"], self.env["stock.picking"]) # vacio: visita sin venta
        if item_venta:
            outcome = self._process_sale(
                cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes,
            )
            vals["sale_order_id"] = outcome.order.id
            if outcome.picking:
                vals["stock_picking_id"] = outcome.picking.id

        withdrawal_outcome = WithdrawalOutcome(self.env["stock.picking"])
        if item_retiro:
            withdrawal_outcome = self._process_withdrawal(
                cliente, reparto, item_retiro, withdrawal_products, withdrawal_lots,
            )
            if withdrawal_outcome.picking:
                vals["withdrawal_picking_id"] = withdrawal_outcome.picking.id

        if linea:
            linea.write(vals)
        else:
            linea = self.env["delivery.route.line"].create({
                **vals,
                "route_id": recorrido.id,
                "client_id": cliente.id,
                "origin": ROUTE_LINE_ORIGIN_OUT_OF_ROUTE if fuera_ruta else ROUTE_LINE_ORIGIN_REVISIT,
                "sequence": max(recorrido.delivery_route_line_ids.mapped("sequence"), default=0) + 1,
            })

        # Fase 6: respuesta
        return self._build_response(linea, outcome, withdrawal_outcome)

    def _resolve_route_line(self, recorrido, cliente, fuera_ruta, visit_date_hour):
        """Elige la linea del recorrido para la visita. Devuelve
        (retry_line, target_line, error).

        Un cliente tiene como maximo dos lineas por recorrido (visita y una
        revisita) y nunca se pisa una que ya tiene visita:
        - retry_line: ya hay una linea del cliente con la misma hora de visita
        (reintento tras un corte); no hay que escribir nada.
        - target_line: primera linea sin visita. Vacia si hay que crear una:
        con fuera_ruta=true la visita fuera de ruta, con fuera_ruta=false la
        revisita (tambien de un cliente que entro como fuera de ruta).
        - fuera_ruta=true exige que el cliente no tenga lineas; false, que tenga.
        - Una tercera visita es error."""
        lines = self.env["delivery.route.line"].search([
            ("route_id", "=", recorrido.id),
            ("client_id", "=", cliente.id),
            ("origin", "!=", "rastrillo"),
        ], order="sequence, id")
        none = lines.browse()
        retry_line = lines.filtered(lambda l: l.visit_date_hour == visit_date_hour)[:1]
        if retry_line:
            return retry_line, none, False

        if fuera_ruta and lines:
            return none, none, "El cliente %s ya tiene linea en el recorrido; no puede enviarse como fuera de ruta." % cliente.customer_code
        if not fuera_ruta and not lines:
            return none, none, "El cliente %s no pertenece al recorrido del reparto %s." % (
                cliente.customer_code, recorrido.delivery_number_id.location_id.aguas_idreparto,
            )
        free = lines.filtered(lambda l: not any(l[field] for field in ROUTE_LINE_VISIT_FIELDS))[:1]
        if not free and ROUTE_LINE_ORIGIN_REVISIT in lines.mapped("origin"):
            return none, none, "El cliente %s ya tiene visita y revisita en el recorrido del reparto %s." % (
                cliente.customer_code, recorrido.delivery_number_id.location_id.aguas_idreparto,
            )
        return none, free, False

    def _process_withdrawal(self, cliente, reparto, item_retiro, products_by_code, lot_by_key):
        """Crea el picking de retiro, lo confirma y lo valida; cada etapa va en
        su propio savepoint y los fallos se informan como warning sin tumbar la
        visita. Si falla la creacion no queda picking. Si falla la confirmacion
        el picking queda en borrador, vinculado a la linea y con una nota con
        el error y los datos del retiro. Si falla la validacion queda asignado."""
        outcome = WithdrawalOutcome(self.env["stock.picking"])
        wanted = self._group_withdrawal_items(item_retiro, products_by_code)
        try:
            with self.env.cr.savepoint():
                outcome.picking = self._create_withdrawal_picking(cliente, reparto, wanted)
        except UserError as e:
            outcome.create_error = str(e)
            return outcome
        try:
            with self.env.cr.savepoint():
                self._confirm_withdrawal_picking(outcome.picking, wanted, lot_by_key)
        except UserError as e:
            outcome.confirm_error = str(e)
            # Fuera del savepoint: la nota debe persistir aunque la confirmacion se revierta
            outcome.picking.message_post(
                body="La confirmacion automatica desde la app fallo y el picking quedo en borrador: %s. Datos del retiro: %s" % (
                    e, self._describe_withdrawal(wanted),
                )
            )
            return outcome
        outcome.validate_error = self._validate_picking(outcome.picking)
        if outcome.validate_error:
            outcome.picking.message_post(
                body="La validacion automatica desde la app fallo y el picking quedo sin validar: %s" % outcome.validate_error
            )
        return outcome

    def _group_withdrawal_items(self, item_retiro, products_by_code):
        """Agrupa los items por (producto, estado de envase): los repetidos se
        suman, y action_confirm no los fusiona por su cuenta.
        Devuelve {(product_id, estado): {"product", "qty", "series"}}."""
        wanted = {}
        for item in item_retiro:
            product = products_by_code[item["retiro_cod_producto"]]
            state = CONTAINER_STATE[item["retiro_tipo"]] if requires_container_state(product) else False
            entry = wanted.setdefault((product.id, state), {"product": product, "qty": 0, "series": []})
            entry["qty"] += item["retiro_cantidad"]
            entry["series"] += item.get("retiro_series") or []
        return wanted

    def _describe_withdrawal(self, wanted):
        """Texto con los datos del retiro, para la nota del picking."""
        parts = []
        for (_product_id, state), entry in wanted.items():
            text = "%s x%s" % (entry["product"].default_code, entry["qty"])
            if state:
                text += " (%s)" % state
            if entry["series"]:
                text += " series: %s" % ", ".join(entry["series"])
            parts.append(text)
        return "; ".join(parts)

    def _create_withdrawal_picking(self, cliente, reparto, wanted):
        """Picking de recepcion del cliente al camion, sin vinculo con la venta,
        en borrador y con un move por (producto, estado). wanted: ver
        _group_withdrawal_items. Patron de water.container.transfer._create_done_picking."""
        location_dest = reparto.location_id
        location = cliente.property_stock_customer
        picking = self.env["stock.picking"].create({
            "picking_type_id": location_dest.warehouse_id.in_type_id.id,
            "partner_id": cliente.id,
            "location_id": location.id,
            "location_dest_id": location_dest.id,
            "move_ids": [Command.create({
                "product_id": product.id,
                "product_uom_qty": entry["qty"],
                "product_uom": product.uom_id.id,
                "location_id": location.id,
                "location_dest_id": location_dest.id,
                "container_state": state,
            }) for (_product_id, state), entry in wanted.items() for product in [entry["product"]]],
        })
        return picking

    def _confirm_withdrawal_picking(self, picking, wanted, lot_by_key):
        """Confirma el picking y fija lotes o cantidades de cada move, dejandolo
        listo para validar. lot_by_key: {(product_template_id, serie): lote},
        como lo arma _withdrawal_availability."""
        picking.action_confirm()
        for move in picking.move_ids:
            entry = wanted[(move.product_id.id, move.container_state or False)]
            # Con serie se fija cada unidad por su lote; sin serie, la cantidad.
            if move.has_tracking == "serial":
                move.lot_ids = [Command.set([
                    lot_by_key[(move.product_id.product_tmpl_id.id, serie)].id for serie in entry["series"]
                ])]
            else:
                move.quantity = entry["qty"]
            move.picked = True

    def _withdrawal_products(self, codes, cliente):
        """Productos a retirar por default_code, sin filtrar show_in_app ni
        sale_ok: se retira lo que el cliente tiene, aunque ya no se venda.
        Con codigo duplicado se prefiere el producto del que el cliente tiene
        envases; entre iguales, el mas antiguo."""
        candidates = self.env["product.product"].search([("default_code", "in", list(codes))], order="id")
        held_templates = set(self.env["water.container"].search([
            ("partner_id", "=", cliente.id),
            ("product_id", "in", candidates.product_tmpl_id.ids),
            ("quantity", ">", 0),
        ]).product_id.ids)
        products_by_code = {}
        for product in candidates:
            code = product.default_code
            current = products_by_code.get(code)
            if current is None:
                products_by_code[code] = product
                continue

            # Codigo duplicado: reemplaza al actual solo si es el que el cliente tiene
            new_is_held = product.product_tmpl_id.id in held_templates
            current_is_held = current.product_tmpl_id.id in held_templates
            if new_is_held and not current_is_held:
                products_by_code[code] = product
        return products_by_code

    def _withdrawal_availability(self, cliente, products):
        """Lee una sola vez los envases del cliente para los productos dados.
        Es el estado previo a la venta de la misma request."""
        containers = self.env["water.container"].search([
            ("partner_id", "=", cliente.id),
            ("product_id", "in", products.product_tmpl_id.ids),
            ("quantity", ">", 0),
        ])
        quantity = {}
        lots = {}
        for container in containers:
            # VERIFICAR lineas x un mismo cliente con mismo product_id y mismo state: se suman cantidades.
            key = (container.product_id.id, container.state)
            quantity[key] = quantity.get(key, 0) + container.quantity
            if container.lot_id:
                lots[(container.product_id.id, container.lot_id.name)] = container.lot_id
        return WithdrawalAvailability(quantity, lots)

    def _process_sale(self, cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes):
        """Crea la venta, la confirma y prepara y valida su picking.
        Confirmar y validar son best effort: la venta ya ocurrio, asi que si
        fallan se registra el error y se sigue."""
        order = self._create_sale_order(
            cliente, reparto, recorrido, item_venta, products_by_code, lot_by_key, duplicated_codes,
        )
        outcome = SaleOutcome(order, self.env["stock.picking"])
        outcome.confirm_error = self._confirm_sale_order(order)
        outcome.picking = order.picking_ids.filtered(lambda p: p.picking_type_code == "outgoing")[:1]
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
                container_state = CONTAINER_STATE[item["tipo_venta"]]
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

    def _build_response(self, linea, sale_outcome, withdrawal_outcome):
        result = {"success": True, "route_line_id": linea.id}
        warnings = []
        if sale_outcome.order:
            result["sale_order_id"] = sale_outcome.order.id
            result["sale_order_confirmed"] = not sale_outcome.confirm_error
            result["picking_validated"] = sale_outcome.picking.state == "done"
            # Son excluyentes: sin confirmacion no hay picking que validar
            if sale_outcome.confirm_error:
                warnings.append("No se pudo confirmar la venta: %s" % sale_outcome.confirm_error)
            elif sale_outcome.validate_error:
                warnings.append("No se pudo validar el picking: %s" % sale_outcome.validate_error)
        if withdrawal_outcome.picking or withdrawal_outcome.create_error:
            result["withdrawal_picking_id"] = withdrawal_outcome.picking.id
            result["withdrawal_picking_validated"] = withdrawal_outcome.picking.state == "done"
            # Son excluyentes: sin picking no hay que confirmar, y sin confirmar no hay que validar
            if withdrawal_outcome.create_error:
                warnings.append("No se pudo crear el retiro de envases: %s" % withdrawal_outcome.create_error)
            elif withdrawal_outcome.confirm_error:
                warnings.append("No se pudo confirmar el picking de retiro (quedo en borrador): %s" % withdrawal_outcome.confirm_error)
            elif withdrawal_outcome.validate_error:
                warnings.append("No se pudo validar el picking de retiro: %s" % withdrawal_outcome.validate_error)
        if warnings:
            result["warning"] = "; ".join(warnings)
        return result

    def _build_retry_response(self, linea):
        """Respuesta de un reintento, armada con el estado actual de la linea:
        mismas claves que la original, sin warning."""
        result = {"success": True, "route_line_id": linea.id}
        if linea.sale_order_id:
            result["sale_order_id"] = linea.sale_order_id.id
            result["sale_order_confirmed"] = linea.sale_order_id.state == "sale"
            result["picking_validated"] = linea.stock_picking_id.state == "done"
        if linea.withdrawal_picking_id:
            result["withdrawal_picking_id"] = linea.withdrawal_picking_id.id
            result["withdrawal_picking_validated"] = linea.withdrawal_picking_id.state == "done"
        return result

    def _app_datetime_to_utc(self, fecha, hora):
        """Convierte fecha YYYY-MM-DD + hora HHMM (hora de Argentina) a UTC naive.
        Lanza ValueError si el formato es invalido."""
        local = datetime.strptime(fecha + " " + hora, APP_DATETIME_FORMAT)
        tz = pytz.timezone(APP_TIMEZONE)
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
