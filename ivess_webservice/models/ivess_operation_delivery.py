from odoo import Command, fields, api, models
from odoo.exceptions import UserError
from datetime import datetime
import pytz


class IvessOperationDelivery(models.AbstractModel):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        # Cabecera basica: obligatoria en cualquier operacion.
        basic_header = {
            "usuario_reparto": str,
            "fecha_operacion": str,
            "nro_reparto": int,
            "hora_atencion": str,
            "hora_envio": str,
            "codigo_cliente": str,
            "motivo_no_compra": int,
            "longitud": str,
            "latitud": str,
            "metros": (int, float),
            "fuera_ruta": bool,
        }
        # Caso venta (motivo_no_compra == 0).
        sale = {
            "item_venta": list,
        }
        # Estructura de cada elemento de item_venta.
        # Numericos aceptan int o float: en JSON un 2 llega como int.
        sale_item = {
            "codigo_producto": str,
            "cantidad": (int, float),
            "precio_venta": (int, float),
        }
        # tipo_venta es opcional a nivel parametro (solo aplica a productos
        # retornables, ver validacion contra el producto) y por eso no esta en
        # sale_item, que _check_params trata como obligatorio.
        # Valor de la app -> water.container.state.
        container_state_by_tipo_venta = {
            "V": "en_comodato",
            "P": "prestado",
        }

        # La app puede no lograr calcular los metros y enviarlos como null
        if "metros" in kwargs and ((kwargs["metros"] is None) or (kwargs["metros"] == 0)):
            kwargs["metros"] = -1

        # Fase 1: cabecera basica. Va primero porque motivo_no_compra
        # define el caso y, por ende, que otros parametros se esperan.
        errors = self._check_params(kwargs, basic_header)
        if errors["missing"]:
            return {"error" : "Faltan parametros obligatorios: %s" % ", ".join(errors["missing"])}
        if errors["invalid_types"]:
            return {"error" : "Tipo invalido en parametros: %s" % ", ".join(errors["invalid_types"])}

        case_schema = {}
        if kwargs["motivo_no_compra"] == 0:
            case_schema.update(sale)
        expected_params_types = {**basic_header, **case_schema}

        unknown_params = set(kwargs) - set(expected_params_types)
        if unknown_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        # Fase 2: parametros propios del caso
        errors = self._check_params(kwargs, case_schema)
        unknown_item_params = []
        invalid_values = []
        if type(kwargs.get("item_venta")) is list:
            for index, item in enumerate(kwargs["item_venta"]):
                if type(item) is not dict:
                    errors["invalid_types"].append("item_venta[%s] (dict)" % index)
                    continue
                prefix = "item_venta[%s]." % index
                unknown_keys = set(item) - set(sale_item) - {"tipo_venta"}
                # evaluar implementar condicion if unknown_keys
                for param in sorted(unknown_keys):
                    unknown_item_params.append(prefix + param)
                item_errors = self._check_params(item, sale_item, prefix)
                errors["missing"] += item_errors["missing"]
                errors["invalid_types"] += item_errors["invalid_types"]
                # None equivale a no enviado (la app puede mandar null en
                # productos no retornables); cualquier otro valor se valida.
                tipo_venta = item.get("tipo_venta")
                if tipo_venta is not None:
                    if type(tipo_venta) is not str:
                        errors["invalid_types"].append(prefix + "tipo_venta (str)")
                    elif tipo_venta not in container_state_by_tipo_venta:
                        invalid_values.append(prefix + "tipo_venta (%s)" % "/".join(container_state_by_tipo_venta))
                if item_errors["missing"] or item_errors["invalid_types"]:
                    continue
                if item["cantidad"] <= 0:
                    invalid_values.append(prefix + "cantidad (> 0)")
                if item["precio_venta"] < 0:
                    invalid_values.append(prefix + "precio_venta (>= 0)")

        if unknown_item_params:
            return {"error" : "Parametros no reconocidos: %s" % ", ".join(unknown_item_params)}
        if errors["missing"]:
            return {"error" : "Faltan parametros obligatorios: %s" % ", ".join(errors["missing"])}
        if errors["invalid_types"]:
            return {"error" : "Tipo invalido en parametros: %s" % ", ".join(errors["invalid_types"])}
        if invalid_values:
            return {"error" : "Valor invalido en parametros: %s" % ", ".join(invalid_values)}

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

        # Validaciones de la venta antes de cualquier escritura: un return
        # de error no hace rollback de lo ya escrito.
        products_by_code = {}
        duplicated_codes = {}
        if item_venta:
            if linea.sale_order_id:
                return {"error": "El cliente %s ya tiene una venta registrada en el recorrido (%s)." % (codigo_cliente, linea.sale_order_id.name)}

            # El almacen de la orden sale de la ubicacion del reparto: sin
            # almacen no se puede determinar el tipo de operacion del picking.
            if not ubicacion.warehouse_id:
                return {"error": "La ubicacion del reparto %s no pertenece a ningun almacen." % aguas_idreparto}

            codes = {item["codigo_producto"] for item in item_venta}
            products = self.env["product.product"].search([
                ("default_code", "in", list(codes)),
                ("product_tmpl_id.show_in_app", "=", True),
            ], order="id")
            for product in products:
                # default_code deberia ser unico por regla de negocio, pero Odoo
                # no lo garantiza (sin constraint). Ante un duplicado se toma el
                # mas antiguo (products viene ordenado por id) y se deja aviso
                # en la orden para revision.
                code = product.default_code
                if code not in products_by_code:
                    products_by_code[code] = product
                else:
                    duplicated_codes.setdefault(code, [products_by_code[code]]).append(product)

            missing_codes = codes - set(products_by_code)
            if missing_codes:
                return {"error": "No existen productos con los codigos: %s" % ", ".join(sorted(missing_codes))}

            # tipo_venta define el estado del envase: solo tiene sentido (y es
            # obligatorio) en productos retornables.
            missing_tipo_venta = []
            unexpected_tipo_venta = []
            for index, item in enumerate(item_venta):
                product = products_by_code[item["codigo_producto"]]
                has_tipo_venta = item.get("tipo_venta") is not None
                if product.is_returnable and not product.is_frio_calor and not has_tipo_venta:
                    missing_tipo_venta.append("item_venta[%s].tipo_venta (%s es retornable)" % (index, product.default_code))
                elif not product.is_returnable and has_tipo_venta:
                    unexpected_tipo_venta.append("item_venta[%s].tipo_venta (%s no es retornable)" % (index, product.default_code))
            if missing_tipo_venta:
                return {"error": "Faltan parametros obligatorios: %s" % ", ".join(missing_tipo_venta)}
            if unexpected_tipo_venta:
                return {"error": "Parametros no aplicables: %s" % ", ".join(unexpected_tipo_venta)}

        vals = {
            "no_purchase_reason_id": motivo_no_compra.id,
            "visit_date_hour": visit_date_hour,
            "delivery_date_hour": phone_date_hour,
            "longitude": longitud,
            "latitude": latitud,
            "meters": str(metros),
            "app_user": usuario_reparto,
        }

        sale_order = self.env["sale.order"]
        picking = self.env["stock.picking"]
        confirm_error = False
        validate_error = False
        if item_venta:
            # El precio de la app es absoluto: discount en 0 evita que
            # pricelist_custom aplique el descuento del cliente encima.
            # container_state solo aplica a retornables no frio/calor y viaja
            # en la linea para que llegue al move aunque la confirmacion falle.
            order_lines = []
            for item in item_venta:
                product = products_by_code[item["codigo_producto"]]
                container_state = False
                if product.is_returnable and not product.is_frio_calor:
                    container_state = container_state_by_tipo_venta[item["tipo_venta"]]
                order_lines.append(Command.create({
                    "product_id": product.id,
                    "product_uom_qty": item["cantidad"],
                    "price_unit": item["precio_venta"],
                    "discount": 0.0,
                    "container_state": container_state,
                }))
            sale_order = sale_order.create({
                "partner_id": cliente.id,
                "warehouse_id": ubicacion.warehouse_id.id,
                "delivery_route_id": recorrido.id,
                "order_line": order_lines,
            })
            if duplicated_codes:
                sale_order.message_post(body="#REVISAR Codigos de producto repetidos: se tomo el producto mas antiguo. %s" % "; ".join(
                    "%s: tomado id %s, descartados ids %s" % (
                        code, candidates[0].id, ", ".join(str(p.id) for p in candidates[1:]),
                    ) for code, candidates in sorted(duplicated_codes.items())
                ))
            # La venta ya ocurrio: si la confirmacion falla (casi siempre por
            # configuracion de Odoo, no por los datos enviados) se deshace solo
            # lo que ella hizo, la orden queda en borrador y se vincula igual.
            try:
                with self.env.cr.savepoint():
                    sale_order.action_confirm()
            except UserError as e:
                confirm_error = str(e)
                sale_order.message_post(
                    body="La confirmacion automatica desde la app fallo y la orden quedo en borrador: %s" % confirm_error
                )
            vals["sale_order_id"] = sale_order.id
            # Solo hay picking si la confirmacion prosperó (y si la orden tiene
            # productos almacenables: una orden solo de servicios no genera ninguno).
            picking = sale_order.picking_ids[:1]
            if picking:
                vals["stock_picking_id"] = picking.id
                # Preparacion fuera de savepoint: son datos de la request (origen
                # en el camion, cantidad vendida) y deben persistir aunque la
                # validacion falle, para que una validacion manual sea correcta.
                # La confirmacion reservo en el almacen: hay que liberar y reservar
                # de nuevo. write() del picking propaga la ubicacion a sus moves.
                picking.do_unreserve()
                picking.write({"location_id": reparto.location_id.id})
                picking.action_assign()
                shortage = picking.move_ids.filtered(lambda m: m.state != "assigned")
                if shortage and not reparto.allow_sale_without_stock:
                    validate_error = "Stock insuficiente en la ubicacion del reparto para completar el picking %s." % picking.name
                else:
                    if shortage:
                        picking.message_post(body="Stock insuficiente en la ubicacion del reparto: se forzo la cantidad vendida. %s" % "; ".join(
                            "%s: reservado %s de %s" % (move.product_id.display_name, move.quantity, move.product_uom_qty)
                            for move in shortage
                        ))
                        for move in shortage:
                            move.quantity = move.product_uom_qty
                    # Mismo criterio que la confirmacion: si la validacion falla se
                    # deshace solo ella, el picking queda sin validar y vinculado.
                    try:
                        with self.env.cr.savepoint():
                            # skip_backorder: sin esto button_validate devuelve el
                            # wizard de backorder. Puede devolver acciones de
                            # impresion, por eso el exito se verifica por el estado.
                            picking.with_context(
                                skip_backorder=True,
                                picking_ids_not_to_backorder=picking.ids,
                            ).button_validate()
                            if picking.state != "done":
                                raise UserError("No se pudo validar el picking %s (estado: %s)." % (picking.name, picking.state))
                    except UserError as e:
                        validate_error = str(e)
                if validate_error:
                    picking.message_post(
                        body="La validacion automatica desde la app fallo y el picking quedo sin validar: %s" % validate_error
                    )

        if fuera_ruta:
            linea = self.env["delivery.route.line"].create({
                **vals,
                "route_id": recorrido.id,
                "client_id": cliente.id,
            })
        else:
            linea.write(vals)

        result = {"success": True, "route_line_id": linea.id}
        if sale_order:
            result["sale_order_id"] = sale_order.id
            result["sale_order_confirmed"] = not confirm_error
            result["picking_validated"] = picking.state == "done"
            # Son excluyentes: sin confirmacion no hay picking que validar
            if confirm_error:
                result["warning"] = "No se pudo confirmar la venta: %s" % confirm_error
            elif validate_error:
                result["warning"] = "No se pudo validar el picking: %s" % validate_error
        return result

    def _check_params(self, params, schema, prefix=""):
        """Valida params contra schema ({param: tipo | tupla de tipos}).
        Solo revisa las keys del schema; las desconocidas se controlan aparte.
        Devuelve {"missing": [...], "invalid_types": [...]}."""
        missing = []
        invalid_types = []
        for param, expected_types in schema.items():
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)
            value = params.get(param)
            if value is None or value == "" or value == []:
                missing.append(prefix + param)
            # type() y no isinstance(): bool es subclase de int
            elif type(value) not in expected_types:
                invalid_types.append("%s%s (%s)" % (
                    prefix, param, "/".join(t.__name__ for t in expected_types),
                ))
        return {"missing": missing, "invalid_types": invalid_types}
