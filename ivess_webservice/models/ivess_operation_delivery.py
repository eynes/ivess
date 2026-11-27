from dataclasses import dataclass
from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from datetime import datetime
import pytz

from ..utils.delivery_params import (
    BASIC_HEADER_SCHEMA,
    COLLECTION_DETAIL,
    CONTAINER_STATE,
    REPLACEMENT_ITEMS,
    REPLACEMENT_REASON_KEY,
    SALE_ITEMS,
    WITHDRAWAL_ITEMS,
    CustomerContainers,
    case_param_names,
    comodato_sale_products,
    comodato_withdrawal_items,
    requested_quantity,
    requires_container_state,
    validate_allows_replacement,
    validate_case_params,
    validate_customer_availability,
    validate_header,
    validate_is_container,
    validate_series,
    validate_series_overlap,
    validate_tipo,
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
    "replacement_out_picking_id",
    "replacement_in_picking_id",
    "comodato_withdrawal_picking_id",
    "replacement_reason_id",
    "cobranza_id",
)


@dataclass
class PickingOutcome:
    """Resultado de un picking de envases (retiro, o un lado del recambio):
    el picking en borrador y el error no fatal. Sin picking y con
    create_error, no se llego a crear."""
    picking: models.BaseModel
    create_error: str | bool = False


@dataclass
class ReplacementOutcome:
    """Resultado del recambio de envases: el picking de salida (envase
    entregado al cliente) y el de entrada (envase recibido del cliente)."""
    out: PickingOutcome
    in_: PickingOutcome


@dataclass
class CollectionOutcome:
    """Resultado de la cobranza: el cobro y errores no fatales. Sin cobro y con
    create_error, no se llego a crear. Con cobro y validate_error, quedo en
    borrador sin validar (error al validar o periodo contable cerrado). Un
    cheque o una retencion quedan en borrador por diseno, sin error."""
    order: models.BaseModel
    create_error: str | bool = False
    validate_error: str | bool = False


class IvessOperationDelivery(models.AbstractModel):
    _name = "ivess.operation.delivery"
    _description = "Servicio de envio de movimientos de ivess"

    @api.model
    def send_operation(self, **kwargs):
        """Registra la visita de un reparto: con venta o con motivo de no compra,
        y en ambos casos con o sin retiro y recambio de envases y con o sin
        cobranza (ninguno de los tres va solo).

        La venta y los pickings se crean en borrador: se confirman y validan al
        cerrar el recorrido. La cobranza se crea y, si es efectivo, se valida.

        Fases: validar parametros -> resolver registros (ubicacion, reparto,
        cliente, motivo de recambio, recorrido) y la linea de la visita (un
        reintento responde sin escribir) -> validar la venta, el retiro y el
        recambio contra productos, series y envases del cliente -> crear la
        venta -> crear el picking de retiro -> si la venta es en comodato
        (tipo 'V', sin serie), crear un picking de retiro aparte con los envases
        que el cliente devuelve a cambio, hasta lo que tenga
        (comodato_withdrawal_picking_id) -> crear los pickings del recambio
        (salida del envase entregado y entrada del recibido) -> crear el cobro
        del cliente y validarlo si es efectivo -> escribir o crear la linea del
        recorrido -> responder con el id de cada documento creado.

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
        item_venta = kwargs.get(SALE_ITEMS.list_key) or []
        item_retiro = kwargs.get(WITHDRAWAL_ITEMS.list_key) or []
        item_recambio = kwargs.get(REPLACEMENT_ITEMS.list_key) or []
        motivo_recambio_id = kwargs.get(REPLACEMENT_REASON_KEY)
        cobrado = kwargs.get("cobrado")
        detalle_valores = kwargs.get("detalle_valores")
        numero_recibo = kwargs.get("numero_recibo")

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

        if item_recambio:
            motivo_recambio = self.env["replacement.reason"].search([("id", "=", motivo_recambio_id)], limit=1)
            if not motivo_recambio:
                return {"error": "No existe motivo de recambio con id: %s" % motivo_recambio_id}

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

        # Fase 4: validar venta, retiro y recambio contra la base (productos,
        # series y envases del cliente). Solo lee: un error se devuelve sin escribir.
        if (item_venta or item_retiro or item_recambio) and not ubicacion.warehouse_id:
            return {"error": "La ubicacion del reparto %s no pertenece a ningun almacen." % aguas_idreparto}

        products_by_code = {}
        sale_containers = {}  # {codigo: producto envase}: el componente retornable si el producto es un kit
        sale_series = set()
        if item_venta:
            codes = {item[SALE_ITEMS.code] for item in item_venta}
            products = self.env["product.product"].search([
                ("default_code", "in", list(codes)),
                ("product_tmpl_id.show_in_app", "=", True),
                ("sale_ok", "=", True),
            ], order="id")
            for product in products:
                products_by_code.setdefault(product.default_code, product)

            missing_codes = codes - set(products_by_code)
            if missing_codes:
                return {"error": "No existen productos con los codigos: %s" % ", ".join(sorted(missing_codes))}

            # El botellon es un kit: el tipo de envase y el estado salen de su componente retornable
            sale_containers, error = self._container_products(products_by_code)
            if error:
                return {"error": error}

            error = validate_tipo(item_venta, sale_containers).message()
            if error:
                return {"error": error}

            series_errors, sale_series = validate_series(item_venta, products_by_code)
            error = series_errors.message()
            if error:
                return {"error": error}

        # Retiro y recambio comparten productos y envases del cliente: se buscan
        # y validan juntos, porque la demanda sobre el cliente (retiro + recibido) se suma.
        # La venta en comodato tambien entra: necesita el estado del cliente para
        # calcular su retiro automatico.
        comodato_products = comodato_sale_products(item_venta, sale_containers) if item_venta else {}
        container_products = {}
        customer_lots = {}
        delivered_series = set()
        comodato_items = []
        if item_retiro or item_recambio or comodato_products:
            flows = [
                (spec, items)
                for spec, items in ((WITHDRAWAL_ITEMS, item_retiro), (REPLACEMENT_ITEMS, item_recambio))
                if items
            ]
            codes = set()
            for spec, items in flows:
                for item in items:
                    codes.add(item[spec.code])
            # flow_products: el producto como lo manda la app (kit o envase); de el sale
            # allows_replacement. container_products: el producto envase (el componente
            # retornable si es un kit); de el sale todo lo demas.
            flow_products = self._withdrawal_products(codes)
            missing_codes = codes - set(flow_products)
            if missing_codes:
                flow_names = " o ".join(
                    name for name, items in (("retiro", item_retiro), ("recambio", item_recambio)) if items
                )
                return {"error": "No existen productos de %s con los codigos: %s" % (flow_names, ", ".join(sorted(missing_codes)))}
            container_products, error = self._container_products(flow_products)
            if error:
                return {"error": error}
            # Los de la venta en comodato se suman para entrar al snapshot del cliente
            # y para que la fase 5 los encuentre al armar el picking.
            for code, product in comodato_products.items():
                container_products.setdefault(code, product)

            for spec, items in flows:
                error = (
                    validate_is_container(items, container_products, spec).message()
                    or validate_allows_replacement(items, flow_products, spec).message()
                    or validate_tipo(items, container_products, spec).message()
                )
                if error:
                    return {"error": error}

            withdrawal_series, received_series = set(), set()
            if item_retiro:
                series_errors, withdrawal_series = validate_series(item_retiro, container_products, WITHDRAWAL_ITEMS)
                error = series_errors.message()
                if error:
                    return {"error": error}
            if item_recambio:
                series_errors, delivered_series = validate_series(item_recambio, container_products, REPLACEMENT_ITEMS)
                error = series_errors.message()
                if error:
                    return {"error": error}
                series_errors, received_series = validate_series(
                    item_recambio, container_products, REPLACEMENT_ITEMS, REPLACEMENT_ITEMS.series_received,
                )
                error = series_errors.message()
                if error:
                    return {"error": error}

            # Una serie no puede estar en dos lados de la request a la vez.
            error = (
                validate_series_overlap(
                    delivered_series, received_series,
                    REPLACEMENT_ITEMS.series, REPLACEMENT_ITEMS.series_received,
                ).message()
                or validate_series_overlap(
                    withdrawal_series, received_series,
                    WITHDRAWAL_ITEMS.series, REPLACEMENT_ITEMS.series_received,
                ).message()
                or validate_series_overlap(
                    sale_series, delivered_series,
                    SALE_ITEMS.series, REPLACEMENT_ITEMS.series,
                ).message()
            )
            if error:
                return {"error": error}

            demands = []
            if item_retiro:
                demands.append((WITHDRAWAL_ITEMS, WITHDRAWAL_ITEMS.series, item_retiro))
            if item_recambio:
                demands.append((REPLACEMENT_ITEMS, REPLACEMENT_ITEMS.series_received, item_recambio))
            products_to_check = self.env["product.product"].union(*container_products.values()) # recordset de envases involucrados
            containers = self._customer_containers(cliente, products_to_check)
            error = validate_customer_availability(demands, container_products, containers).message()
            if error:
                return {"error": error}
            customer_lots = containers.lots

            # Retiro automatico de la venta en comodato: lo explicito va primero
            # (ya validado arriba) y el automatico toma lo que le queda al cliente.
            if comodato_products:
                comodato_items = comodato_withdrawal_items(
                    item_venta, sale_containers, containers,
                    requested_quantity(demands, container_products),
                )

        # Lotes de las series de la venta y del envase entregado: una sola busqueda.
        lot_by_key = {}
        requested_series = sale_series | delivered_series
        if requested_series:
            lots = self.env["stock.lot"].search(Domain.OR(
                [("product_id", "=", product_id), ("name", "=", serie)]
                for product_id, serie in requested_series
            ), order="id desc")
            lot_by_key = {(lot.product_id.id, lot.name): lot for lot in lots}
            missing_series = requested_series - set(lot_by_key)
            if missing_series:
                code_by_product_id = {
                    product.id: code
                    for code, product in [*products_by_code.items(), *container_products.items()]
                }
                unknown_series = sorted(
                    "%s (%s)" % (serie, code_by_product_id[product_id])
                    for product_id, serie in missing_series
                )
                return {"error": "No existen numeros de serie: %s" % ", ".join(unknown_series)}

        # El envase entregado no puede ser ya de un cliente (incluido este).
        if delivered_series:
            assigned = self.env["water.container"].search([
                ("lot_id", "in", [lot_by_key[key].id for key in delivered_series]),
                ("quantity", ">", 0),
            ])
            if assigned:
                return {"error": "Series entregadas ya asignadas a un cliente: %s" % ", ".join(sorted(
                    "%s (%s)" % (container.lot_id.name, container.partner_id.customer_code or container.partner_id.display_name)
                    for container in assigned
                ))}

        # Cobranza: diarios, numero del recibo y periodo contable. Solo lee.
        collection = {}
        if cobrado is not None:
            collection, error = self._resolve_collection(reparto, fecha_operacion, detalle_valores, numero_recibo)
            if error:
                return {"error": error}

        # Fase 5: escribir. Desde aca los fallos ya no cortan el flujo: se
        # informan como warning. Venta, retiro y despues la linea del recorrido.
        # Venta y pickings quedan en borrador: se confirman y validan al cerrar el recorrido.
        vals = {
            "no_purchase_reason_id": motivo_no_compra.id,
            "visit_date_hour": visit_date_hour,
            "delivery_date_hour": phone_date_hour,
            "longitude": longitud,
            "latitude": latitud,
            "meters": str(metros),
            "app_user": usuario_reparto,
        }

        sale_order = self.env["sale.order"]  # vacio: visita sin venta
        if item_venta:
            sale_order = self._create_sale_order(
                cliente, reparto, recorrido, item_venta, products_by_code, sale_containers, lot_by_key,
            )
            vals["sale_order_id"] = sale_order.id

        withdrawal_outcome = PickingOutcome(self.env["stock.picking"])
        if item_retiro:
            withdrawal_outcome = self._process_withdrawal(
                cliente, reparto, item_retiro, container_products, customer_lots,
            )
            if withdrawal_outcome.picking:
                vals["withdrawal_picking_id"] = withdrawal_outcome.picking.id

        # Retiro automatico de la venta en comodato: picking aparte del retiro que
        # informa la app, para distinguirlos en la linea.
        comodato_outcome = PickingOutcome(self.env["stock.picking"])
        if comodato_items:
            comodato_outcome = self._process_withdrawal(
                cliente, reparto, comodato_items, container_products, customer_lots,
            )
            if comodato_outcome.picking:
                vals["comodato_withdrawal_picking_id"] = comodato_outcome.picking.id

        # Recambio: despues del retiro. Salida primero, asi lo recibido no tapa la falta de stock del entregado.
        replacement_outcome = ReplacementOutcome(
            PickingOutcome(self.env["stock.picking"]), PickingOutcome(self.env["stock.picking"]),
        )
        if item_recambio:
            replacement_outcome = self._process_replacement(
                cliente, reparto, item_recambio, container_products, customer_lots, lot_by_key,
            )
            vals["replacement_reason_id"] = motivo_recambio.id
            if replacement_outcome.out.picking:
                vals["replacement_out_picking_id"] = replacement_outcome.out.picking.id
            if replacement_outcome.in_.picking:
                vals["replacement_in_picking_id"] = replacement_outcome.in_.picking.id

        # Cobranza 
        collection_outcome = CollectionOutcome(self.env["account.payment.order"])
        if collection:
            collection_outcome = self._process_collection(cliente, fecha_operacion, cobrado, collection)
            if collection_outcome.order:
                vals["cobranza_id"] = collection_outcome.order.id

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
        return self._build_response(
            linea, sale_order, withdrawal_outcome, comodato_outcome, replacement_outcome, collection_outcome,
        )

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

    def _resolve_collection(self, reparto, fecha_operacion, detalle_valores, numero_recibo):
        """Resuelve lo que necesita la cobranza para crearse sin fallar: el
        diario del cobro, el numero del recibo y el diario o impuesto de la
        linea segun detalle_valores. Solo lee: un error se devuelve sin
        escribir. Devuelve (collection, error); collection tiene "detail" (de
        COLLECTION_DETAIL), "journal", "number" (False si no vino
        numero_recibo) y, segun el detalle, "cash_journal" y "period_error"
        (motivo por el que el efectivo no se puede validar, o False),
        "check_journal" o "tax" y "tax_account".

        Sin numero_recibo el diario es el del reparto (route_number_journal_id);
        con numero_recibo es su talonario de cobranzas (collection_journal_ids,
        que tiene un unico diario). El numero se guarda tal cual vino, sin tocar
        la secuencia del diario."""
        detail = COLLECTION_DETAIL[detalle_valores]
        number = numero_recibo.strip() if numero_recibo is not None else False
        journal = reparto.collection_journal_ids[:1] if number else reparto.route_number_journal_id
        if not journal:
            campo = "talonario de cobranzas" if number else "diario del reparto"
            return {}, "El reparto %s no tiene %s configurado para registrar la cobranza." % (
                reparto.location_id.aguas_idreparto, campo,
            ) 
        if number and self.env["account.payment.order"].search_count([
            ("type", "=", "receipt"),
            ("journal_id", "=", journal.id),
            ("number", "=", number),
        ]):
            return {}, "Ya existe una cobranza con el numero %s en el diario %s." % (number, journal.code)

        collection = {"detail": detail, "journal": journal, "number": number}
        company = journal.company_id
        if detail == "efectivo":
            collection["cash_journal"] = reparto.cash_journal_id
            if not collection["cash_journal"]:
                return {}, "El reparto %s no tiene diario de efectivo configurado." % reparto.location_id.aguas_idreparto
            # Solo el efectivo se valida (contabiliza): los demas quedan en borrador.
            # Un periodo cerrado no corta la visita: el cobro se crea en borrador sin
            # validar y el motivo se informa como warning.
            collection["period_error"] = self._check_journal_period(journal, fields.Date.to_date(fecha_operacion))
        elif detail == "cheque":
            collection["check_journal"] = self.env["account.journal"].search([
                ("type", "=", "third_party_checks"),
                ("company_id", "=", company.id),
            ], limit=1)
            if not collection["check_journal"]:
                return {}, "No existe un diario de cheques de terceros para registrar la cobranza."
        else:
            # Impuesto de retencion de venta cuyo asiento tenga cuenta (get_retention_account lanza error si no).
            for tax in self.env["account.tax"].search([
                ("tax_group_id.group_type", "=", "retention"),
                ("type_tax_use", "=", "sale"),
                ("company_id", "=", company.id),
            ], order="id"):
                try:
                    collection["tax_account"] = tax.get_retention_account()
                except ValidationError:
                    continue
                collection["tax"] = tax
                break
            if "tax" not in collection:
                return {}, "No existe un impuesto de retencion de venta con cuenta para registrar la cobranza."
        return collection, False

    def _check_journal_period(self, journal, fecha):
        """Replica la validacion de ivess_validate_period.account.move._post
        (si el modulo esta instalado) antes de crear el cobro: ante un periodo
        invalido ese modulo hace commit() y despues lanza el error, lo que
        rompe los savepoints y deja el cobro a medio crear. Por eso, con un
        periodo invalido, el cobro no se valida y queda en borrador. Mismo
        chequeo que ivess_invoice_import. Devuelve el motivo o False."""
        if not hasattr(self.env["account.move"], "_validate_period"):
            return False
        if not journal.due_date:
            return "El diario '%s' no tiene fecha de cierre establecida." % journal.code
        if fecha < journal.due_date:
            return "La fecha de la operacion (%s) es anterior a la fecha de cierre del diario '%s' (%s)." % (
                fecha.strftime("%d-%m-%Y"), journal.code, journal.due_date.strftime("%d-%m-%Y"),
            )
        return False

    def _process_collection(self, cliente, fecha_operacion, cobrado, collection):
        """Crea el cobro del cliente y, solo si es efectivo, lo valida. Cada
        etapa va en su propio savepoint y los fallos se informan como warning
        sin tumbar la visita. Si falla la creacion no queda cobro. Un cheque o
        una retencion quedan en borrador con una nota para que una persona
        complete los datos PENDIENTE. El efectivo queda en borrador, con nota,
        si falla la validacion o si el periodo contable esta cerrado.
        collection: ver _resolve_collection."""
        outcome = CollectionOutcome(self.env["account.payment.order"])
        date = fields.Date.to_date(fecha_operacion)
        try:
            with self.env.cr.savepoint():
                outcome.order = self._create_collection_order(cliente, date, cobrado, collection)
        except UserError as e:
            outcome.create_error = str(e)
            return outcome
        if collection["detail"] != "efectivo":
            outcome.order.message_post(
                body="Cobranza cargada desde la app con datos pendientes de completar (%s)" % collection["detail"]
            )
            return outcome
        # Con el periodo cerrado ni se intenta validar: ver _check_journal_period
        outcome.validate_error = collection["period_error"] or self._validate_collection_order(outcome.order)
        if outcome.validate_error:
            outcome.order.message_post(
                body="La validacion automatica desde la app fallo y la cobranza quedo en borrador: %s" % outcome.validate_error
            )
        return outcome

    def _create_collection_order(self, cliente, date, cobrado, collection):
        """Cobro (account.payment.order de tipo receipt) en borrador, con una
        unica linea segun el detalle. Sin facturas imputadas: queda como pago a
        cuenta. Con numero_recibo se fija el numero tal cual; posted_before=True
        evita que proforma_voucher lo pise con la secuencia del diario (mismo
        recurso que ivess_invoice_import). disable_retentions evita el calculo
        automatico de retenciones de anticipo. En cheque y retencion los datos
        que la app no manda van en PENDIENTE o vacios; en Python solo son
        obligatorios el numero, el diario y el formato del cheque."""
        journal = collection["journal"]
        vals = {
            "type": "receipt",
            "partner_id": cliente.id,
            "journal_id": journal.id,
            "company_id": journal.company_id.id,
            "date": date,
            "disable_retentions": True, 
        }
        if collection["number"]:
            vals["number"] = collection["number"]
            vals["posted_before"] = True
        detail = collection["detail"]
        if detail == "efectivo":
            vals["payment_mode_line_ids"] = [Command.create({
                "payment_mode_id": collection["cash_journal"].id,
                "amount": cobrado,
                "date": date,
            })]
        elif detail == "cheque":
            vals["third_party_check_receipt_ids"] = [Command.create({
                "journal_id": collection["check_journal"].id,
                "company_id": journal.company_id.id,
                "number": "00000000",
                "checkbook_format": "physical",
                "amount": cobrado,
                "reception_date": date,
            })]
        else:
            vals["retention_ids"] = [Command.create({
                "retention_id": collection["tax"].id,
                "account_id": collection["tax_account"].id,
                "name": collection["tax"].name,
                "certificate_no": "PENDIENTE",
                "amount": cobrado,
                "date": date,
            })]
        order = self.env["account.payment.order"].create(vals)
        if collection["number"]:
            self._advance_journal_sequence(journal, collection["number"])
        return order

    def _advance_journal_sequence(self, journal, number):
        """Con numero_recibo el cobro no consume la secuencia (posted_before):
        se la sube a max(actual, numero + 1) para que el proximo automatico, y
        el next_number de get_talonarios, no repita un numero ya usado. Se
        escribe en la secuencia con sudo porque el inverse de
        journal.sequence_number_next hace lo mismo y el usuario del servicio no
        puede escribir account.journal."""
        sequence = journal.sequence_id._get_current_sequence().sudo()
        sequence.number_next = max(sequence.number_next_actual, int(number) + 1)

    def _validate_collection_order(self, order):
        """Valida el cobro (genera el asiento contable). Si falla se deshace
        solo la validacion: el cobro queda en borrador y vinculado. Devuelve el
        error o False. proforma_voucher no lanza ante un error al generar el
        asiento: lo captura, deja el cobro en borrador y devuelve un popup, por
        eso el exito se verifica por el estado."""
        try:
            with self.env.cr.savepoint():
                result = order.proforma_voucher()
                if order.state != "posted":
                    message = result.get("context", {}).get("message") if isinstance(result, dict) else None
                    raise UserError(message or "No se pudo validar la cobranza %s." % order.display_name)
        except UserError as e:
            return str(e)
        return False

    def _process_withdrawal(self, cliente, reparto, items, products_by_code, customer_lots,
                            spec=WITHDRAWAL_ITEMS, series_key=None):
        """Crea en borrador el picking de entrada (cliente al camion) del retiro,
        o del lado recibido del recambio (spec y series_key). Si falla la creacion se
        deshace y se informa como warning.
        customer_lots: lotes de los envases del cliente, {(template, serie): lote},
        como lo arma _customer_containers."""
        outcome = PickingOutcome(self.env["stock.picking"])
        wanted = self._group_withdrawal_items(items, products_by_code, spec, series_key)
        try:
            with self.env.cr.savepoint():
                outcome.picking = self._create_container_picking(
                    reparto.location_id.warehouse_id.in_type_id,
                    cliente, cliente.property_stock_customer, reparto.location_id, wanted,
                    lot_field="lot_ids",
                    lot_of=lambda product, serie: customer_lots[(product.product_tmpl_id.id, serie)],
                )
        except UserError as e:
            outcome.create_error = str(e)
        return outcome

    def _group_withdrawal_items(self, items, products_by_code, spec=WITHDRAWAL_ITEMS, series_key=None):
        """Agrupa los items por (producto, estado de envase): los repetidos se
        suman en un solo move. Moves del mismo producto con distinto estado
        quedan separados porque logistic_custom_ivess agrega container_state a
        los campos que impiden la fusion en action_confirm.
        series_key: que lista de series se toma (por defecto spec.series; el
        recambio tiene dos, entregado y recibido).
        Devuelve {(product_id, estado): {"product", "qty", "series"}}."""
        series_key = series_key or spec.series
        wanted = {}
        for item in items:
            product = products_by_code[item[spec.code]]
            state = CONTAINER_STATE[item[spec.tipo]] if requires_container_state(product) else False
            entry = wanted.setdefault((product.id, state), {"product": product, "qty": 0, "series": []})
            entry["qty"] += item[spec.qty]
            entry["series"] += item.get(series_key) or []
        return wanted

    def _create_container_picking(self, picking_type, cliente, location, location_dest, wanted,
                                  lot_field, lot_of):
        """Picking de envases entre location y location_dest, en borrador y con
        un move por (producto, estado). Patron de
        water.container.transfer._create_done_picking.
        lot_field: nombre del campo del move donde se guardan las series. Lo
        elige cada caso: "lot_ids" en un picking de entrada (en borrador no
        reserva nada) y "requested_lot_ids" en uno de salida (lot_ids reservaria
        el stock y sacaria el move de borrador).
        lot_of(producto, serie) -> lote: como buscar el lote de cada serie.
        Las series se asignan despues del create: con lot_ids en el create el
        picking nace asignado y no en borrador; con un write posterior queda en
        borrador y la confirmacion conserva las series.
        wanted: ver _group_withdrawal_items."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
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
        for move in picking.move_ids:
            entry = wanted[(move.product_id.id, move.container_state or False)]
            if entry["series"]:
                move[lot_field] = [Command.set([lot_of(move.product_id, serie).id for serie in entry["series"]])]
        return picking

    def _process_replacement(self, cliente, reparto, item_recambio, products_by_code, customer_lots, lot_by_key):
        """Recambio de envases: dos pickings en borrador por visita. La salida
        (envase entregado, camion al cliente) y la entrada (envase recibido,
        cliente al camion). Cada uno falla por separado, sin tumbar al otro.
        customer_lots: lotes de los envases del cliente (para el recibido);
        lot_by_key: lotes de las series entregadas."""
        out = self._process_replacement_out(cliente, reparto, item_recambio, products_by_code, lot_by_key)
        in_ = self._process_withdrawal(
            cliente, reparto, item_recambio, products_by_code, customer_lots,
            spec=REPLACEMENT_ITEMS, series_key=REPLACEMENT_ITEMS.series_received,
        )
        return ReplacementOutcome(out, in_)

    def _process_replacement_out(self, cliente, reparto, item_recambio, products_by_code, lot_by_key):
        """Crea en borrador el picking de salida del recambio (camion al cliente).
        No lo confirma, no reserva ni controla el stock: eso pasa al cerrar el
        recorrido. Las series entregadas van en requested_lot_ids, porque con
        lot_ids el move reservaria el stock y dejaria de ser borrador. Si falla
        la creacion se deshace y se informa como warning.
        lot_by_key: {(producto, serie): lote} de las series entregadas."""
        outcome = PickingOutcome(self.env["stock.picking"])
        wanted = self._group_withdrawal_items(
            item_recambio, products_by_code, REPLACEMENT_ITEMS, REPLACEMENT_ITEMS.series,
        )
        try:
            with self.env.cr.savepoint():
                outcome.picking = self._create_container_picking(
                    reparto.location_id.warehouse_id.out_type_id,
                    cliente, reparto.location_id, cliente.property_stock_customer, wanted,
                    lot_field="requested_lot_ids",
                    lot_of=lambda product, serie: lot_by_key[(product.id, serie)],
                )
        except UserError as e:
            outcome.create_error = str(e)
        return outcome

    def _withdrawal_products(self, codes):
        """Productos de retiro y recambio por default_code, sin filtrar show_in_app
        ni sale_ok: se retira lo que el cliente tiene, aunque ya no se venda.
        Se asume default_code unico; si hubiera duplicados se toma el mas antiguo."""
        candidates = self.env["product.product"].search([("default_code", "in", list(codes))], order="id")
        products_by_code = {}
        for product in candidates:
            products_by_code.setdefault(product.default_code, product)
        return products_by_code

    def _container_products(self, products_by_code):
        """Producto que hace de envase de cada producto de la request. Devuelve
        ({default_code: producto_envase}, error).

        El botellon es un kit (BoM phantom): el producto que manda la app es el
        kit, pero el envase retornable (el que tiene is_returnable, tipo de
        envase y water.container) es su componente. Para un kit con exactamente
        un componente retornable se devuelve ese componente. Para cualquier otro
        producto (envase comun, frio/calor, kit sin componente retornable, promo)
        se devuelve el mismo producto.

        Con mas de un componente retornable es un error de configuracion: se
        devuelve ({}, mensaje). Solo lee."""
        products = self.env["product.product"].union(*products_by_code.values())
        # sudo como mrp al explotar el kit: el usuario del servicio no tiene por que leer BoMs
        boms = self.env["mrp.bom"].sudo()._bom_find(products, company_id=self.env.company.id, bom_type="phantom")
        container_by_code = {}
        for code, product in products_by_code.items():
            bom = boms.get(product)
            if not bom or product.is_promo:
                container_by_code[code] = product
                continue
            returnable = bom.bom_line_ids.product_id.filtered(lambda p: p.product_tmpl_id.is_returnable)
            if len(returnable) > 1:
                return {}, "El producto %s tiene mas de un componente retornable en su lista de materiales." % code
            # browse con el env del servicio: el componente no debe quedar con sudo
            container_by_code[code] = self.env["product.product"].browse(returnable.id) if returnable else product
        return container_by_code, False

    def _customer_containers(self, cliente, products):
        """Lee una sola vez los envases del cliente para los productos dados.
        Es el estado previo a la venta de la misma request."""
        containers = self.env["water.container"].search([
            ("partner_id", "=", cliente.id),
            ("product_id", "in", products.product_tmpl_id.ids),
            ("quantity", ">", 0),
        ])
        quantity = {}
        lots = {}
        lot_states = {}
        for container in containers:
            # VERIFICAR lineas x un mismo cliente con mismo product_id y mismo state: se suman cantidades.
            key = (container.product_id.id, container.state)
            quantity[key] = quantity.get(key, 0) + container.quantity
            if container.lot_id:
                lot_key = (container.product_id.id, container.lot_id.name)
                lots[lot_key] = container.lot_id
                lot_states[lot_key] = container.state
        return CustomerContainers(quantity, lots, lot_states)

    def _create_sale_order(self, cliente, reparto, recorrido, item_venta, products_by_code, sale_containers, lot_by_key):
        # El precio de la app es absoluto: discount en 0 evita que
        # pricelist_custom aplique el descuento del cliente encima.
        order_lines = []
        for item in item_venta:
            product = products_by_code[item[SALE_ITEMS.code]]   # la linea es del producto vendido (el kit)
            container_state = False
            # el estado de envase lo decide el envase (el componente retornable si es un kit)
            if requires_container_state(sale_containers[item[SALE_ITEMS.code]]):
                container_state = CONTAINER_STATE[item[SALE_ITEMS.tipo]]
            order_lines.append(Command.create({
                "product_id": product.id,
                "product_uom_qty": item[SALE_ITEMS.qty],
                "price_unit": item[SALE_ITEMS.price],
                "discount": 0.0,
                "container_state": container_state,
                "serial_lot_ids": [Command.set([lot_by_key[(product.id, serie)].id for serie in item.get(SALE_ITEMS.series) or []])],
            }))
        order = self.env["sale.order"].create({
            "partner_id": cliente.id,
            "warehouse_id": reparto.location_id.warehouse_id.id,
            "delivery_route_id": recorrido.id,
            "order_line": order_lines,
        })
        return order

    def _build_response(self, linea, sale_order, withdrawal_outcome, comodato_outcome, replacement_outcome, collection_outcome):
        result = {"success": True, "route_line_id": linea.id}
        warnings = []
        if sale_order:
            result["sale_order_id"] = sale_order.id
        if withdrawal_outcome.picking or withdrawal_outcome.create_error:
            result["withdrawal_picking_id"] = withdrawal_outcome.picking.id
            if withdrawal_outcome.create_error:
                warnings.append("No se pudo crear el retiro de envases: %s" % withdrawal_outcome.create_error)
        if comodato_outcome.picking or comodato_outcome.create_error:
            result["comodato_withdrawal_picking_id"] = comodato_outcome.picking.id
            if comodato_outcome.create_error:
                warnings.append("No se pudo crear el retiro automatico por venta en comodato: %s" % comodato_outcome.create_error)
        for key, outcome, label in (
            ("replacement_out", replacement_outcome.out, "entrega"),
            ("replacement_in", replacement_outcome.in_, "retiro"),
        ):
            if not (outcome.picking or outcome.create_error):
                continue
            result[key + "_picking_id"] = outcome.picking.id
            if outcome.create_error:
                warnings.append("No se pudo crear el picking de recambio (%s): %s" % (label, outcome.create_error))
        if collection_outcome.order or collection_outcome.create_error:
            result["payment_order_id"] = collection_outcome.order.id
            result["payment_order_validated"] = collection_outcome.order.state == "posted"
            # Excluyentes, igual que en el retiro. Un cheque o una retencion quedan en
            # borrador por diseno: payment_order_validated en false y sin warning.
            if collection_outcome.create_error:
                warnings.append("No se pudo crear la cobranza: %s" % collection_outcome.create_error)
            elif collection_outcome.validate_error:
                warnings.append("No se pudo validar la cobranza (quedo en borrador): %s" % collection_outcome.validate_error)
        if warnings:
            result["warning"] = "; ".join(warnings)
        return result

    def _build_retry_response(self, linea):
        """Respuesta de un reintento, armada con el estado actual de la linea:
        mismas claves que la original, sin warning."""
        result = {"success": True, "retry": True, "route_line_id": linea.id}
        if linea.sale_order_id:
            result["sale_order_id"] = linea.sale_order_id.id
        if linea.withdrawal_picking_id:
            result["withdrawal_picking_id"] = linea.withdrawal_picking_id.id
        if linea.comodato_withdrawal_picking_id:
            result["comodato_withdrawal_picking_id"] = linea.comodato_withdrawal_picking_id.id
        if linea.replacement_out_picking_id:
            result["replacement_out_picking_id"] = linea.replacement_out_picking_id.id
        if linea.replacement_in_picking_id:
            result["replacement_in_picking_id"] = linea.replacement_in_picking_id.id
        if linea.cobranza_id:
            result["payment_order_id"] = linea.cobranza_id.id
            result["payment_order_validated"] = linea.cobranza_id.state == "posted"
        return result

    def _app_datetime_to_utc(self, fecha, hora):
        """Convierte fecha YYYY-MM-DD + hora HHMM (hora de Argentina) a UTC naive.
        Lanza ValueError si el formato es invalido."""
        local = datetime.strptime(fecha + " " + hora, APP_DATETIME_FORMAT)
        tz = pytz.timezone(APP_TIMEZONE)
        return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
