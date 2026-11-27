from odoo import api, models

from .ivess_operation_delivery import CollectionOutcome, PickingOutcome, ReplacementOutcome
from ..utils.delivery_params import (
    REPLACEMENT_ITEMS,
    REPLACEMENT_REASON_KEY,
    SALE_ITEMS,
    WITHDRAWAL_ITEMS,
    ParamErrors,
    case_param_names,
    check_schema,
    validate_case_params,
)

UPDATE_HEADER_SCHEMA = {
    "route_line_id": int,
    "nro_reparto": int,
}

# Campos de la linea del recorrido con los remitos de envases que crea el servicio.
VISIT_PICKING_FIELDS = (
    "withdrawal_picking_id",
    "comodato_withdrawal_picking_id",
    "replacement_out_picking_id",
    "replacement_in_picking_id",
)
# Un documento cancelado no bloquea la modificacion: se ignora.
EDITABLE_SALE_STATES = ("draft", "sent", "cancel")
EDITABLE_PICKING_STATES = ("draft", "cancel")


class IvessOperationUpdate(models.AbstractModel):
    _inherit = "ivess.operation.delivery"

    @api.model
    def update_operation(self, **kwargs):
        """Modifica una visita ya registrada por send_operation: reemplaza por
        completo el contenido de sus documentos en borrador (venta, retiro,
        retiro por comodato y recambio) con lo que llega. No es un delta: un
        item que no llega se borra.

        Parametros: route_line_id y nro_reparto (obligatorios), item_venta,
        item_retiro, item_recambio y recambio_motivo, con las mismas reglas de
        send_operation. item_venta es obligatorio si la visita es una venta (no
        tiene motivo de no compra) y no aplica si no lo es.

        Fases: validar la cabecera -> resolver el reparto y la linea, y
        rechazar si el recorrido no esta en progreso o algun documento ya no
        esta en borrador -> validar los parametros del caso -> validar los
        items contra la base (igual que send_operation) -> reemplazar el
        contenido de los borradores (crea los que faltan y borra los que ya no
        llegan) y sincronizar el rastrillo -> responder con los ids vigentes.

        Todas las validaciones van antes de cualquier escritura: un return de
        error no hace rollback.
        """
        # Fase 1: cabecera
        errors = ParamErrors()
        check_schema(kwargs, UPDATE_HEADER_SCHEMA, errors)
        error = errors.message()
        if error:
            return {"error": error}

        # Fase 2: resolver reparto y linea, y rechazar lo que ya no se puede modificar
        aguas_idreparto = kwargs["nro_reparto"]
        ubicacion = self.env["stock.location"].search([("aguas_idreparto", "=", aguas_idreparto)], limit=1)
        if not ubicacion:
            return {"error": "No existe ubicacion asociada al nro de reparto provisto."}

        reparto = self.env["delivery.route.number"].search([("location_id", "=", ubicacion.id)], limit=1)
        if not reparto:
            return {"error": "No existe reparto asociado a la ubicacion del nro de reparto provisto."}

        linea, error = self._resolve_update_line(kwargs["route_line_id"], reparto)
        if error:
            return {"error": error}

        # Fase 3: parametros del caso. El motivo de no compra es el de la visita.
        params = {**kwargs, "motivo_no_compra": linea.no_purchase_reason_id.id}
        allowed = set(UPDATE_HEADER_SCHEMA) | (
            case_param_names(params) & {SALE_ITEMS.list_key, WITHDRAWAL_ITEMS.list_key,
                                        REPLACEMENT_ITEMS.list_key, REPLACEMENT_REASON_KEY}
        )
        unknown_params = set(kwargs) - allowed
        if unknown_params:
            return {"error": "Parametros no reconocidos: %s" % ", ".join(sorted(unknown_params))}

        error = validate_case_params(params).message()
        if error:
            return {"error": error}

        item_venta = kwargs.get(SALE_ITEMS.list_key) or []
        item_retiro = kwargs.get(WITHDRAWAL_ITEMS.list_key) or []
        item_recambio = kwargs.get(REPLACEMENT_ITEMS.list_key) or []
        motivo_recambio_id = kwargs.get(REPLACEMENT_REASON_KEY)
        if item_recambio:
            motivo_recambio = self.env["replacement.reason"].search([("id", "=", motivo_recambio_id)], limit=1)
            if not motivo_recambio:
                return {"error": "No existe motivo de recambio con id: %s" % motivo_recambio_id}

        cliente = linea.client_id

        # Fase 4: validar los items contra la base. Solo lee.
        items, error = self._validate_operation_items(cliente, ubicacion, item_venta, item_retiro, item_recambio)
        if error:
            return {"error": error}

        # Fase 5: escribir. Cada documento en borrador conserva su id y se le
        # reemplaza el contenido; el que no existia se crea y el que ya no llega
        # se borra. Un picking que falla se deshace solo y queda como estaba
        # (warning); la venta no tiene savepoint, igual que en send_operation.
        # Un documento cancelado se ignora: no se reutiliza, se crea otro.
        recorrido = linea.route_id
        picking_model = self.env["stock.picking"]
        vals = {}
        discarded = picking_model  # borradores que ya no llegan

        sale_order = self.env["sale.order"]
        if item_venta:
            sale_order = self._create_sale_order(
                cliente, reparto, recorrido, item_venta, items.products_by_code, items.sale_containers,
                items.lot_by_key, order=linea.sale_order_id.filtered(lambda o: o.state in ("draft", "sent")),
            )
            vals["sale_order_id"] = sale_order.id

        withdrawal_outcome = PickingOutcome(picking_model)
        current = linea.withdrawal_picking_id.filtered(lambda p: p.state == "draft")
        if item_retiro:
            withdrawal_outcome = self._process_withdrawal(
                cliente, reparto, item_retiro, items.container_products, items.customer_lots, picking=current,
            )
            vals["withdrawal_picking_id"] = withdrawal_outcome.picking.id
        else:
            vals["withdrawal_picking_id"] = False
            discarded |= current

        comodato_outcome = PickingOutcome(picking_model)
        current = linea.comodato_withdrawal_picking_id.filtered(lambda p: p.state == "draft")
        if items.comodato_items:
            comodato_outcome = self._process_withdrawal(
                cliente, reparto, items.comodato_items, items.container_products, items.customer_lots, picking=current,
            )
            vals["comodato_withdrawal_picking_id"] = comodato_outcome.picking.id
        else:
            vals["comodato_withdrawal_picking_id"] = False
            discarded |= current

        replacement_outcome = ReplacementOutcome(PickingOutcome(picking_model), PickingOutcome(picking_model))
        out_current = linea.replacement_out_picking_id.filtered(lambda p: p.state == "draft")
        in_current = linea.replacement_in_picking_id.filtered(lambda p: p.state == "draft")
        if item_recambio:
            replacement_outcome = self._process_replacement(
                cliente, reparto, item_recambio, items.container_products, items.customer_lots, items.lot_by_key,
                out_picking=out_current, in_picking=in_current,
            )
            vals["replacement_reason_id"] = motivo_recambio.id
            vals["replacement_out_picking_id"] = replacement_outcome.out.picking.id
            vals["replacement_in_picking_id"] = replacement_outcome.in_.picking.id
        else:
            vals["replacement_reason_id"] = False
            vals["replacement_out_picking_id"] = False
            vals["replacement_in_picking_id"] = False
            discarded |= out_current | in_current

        linea.write(vals)
        self._sync_rake_line(linea, vals)
        discarded.unlink()

        # Fase 6: respuesta. Sin cobranza: este servicio no la modifica.
        return self._build_response(
            linea, sale_order, withdrawal_outcome, comodato_outcome, replacement_outcome,
            CollectionOutcome(self.env["account.payment.order"]),
        )

    def _sync_rake_line(self, linea, vals):
        """El rastrillo copia los documentos de la visita que lo genero (un
        motivo de rastrillo o forzar_rastrillo): se le escriben los mismos
        ids, tambien los de documentos nuevos."""
        if not (linea.no_purchase_reason_id.is_rake or linea.forzar_rastrillo):
            return
        self.env["delivery.route.line"].search([
            ("route_id", "=", linea.route_id.id),
            ("client_id", "=", linea.client_id.id),
            ("origin", "=", "rastrillo"),
        ]).write(vals)

    def _resolve_update_line(self, route_line_id, reparto):
        """Linea de la visita a modificar. Devuelve (linea, error). Solo lee.

        Se rechaza si la linea no existe, es un rastrillo (copia los
        documentos de la visita original, que es la que se modifica), no es
        del reparto que llega, no tiene visita registrada (para eso esta
        send_operation), o su recorrido no esta en progreso. Despues se
        controlan los documentos de la visita."""
        linea = self.env["delivery.route.line"].search([("id", "=", route_line_id)], limit=1)
        if not linea:
            return linea, "No existe la visita con id: %s" % route_line_id
        if linea.origin == "rastrillo":
            return linea, "La visita %s es un rastrillo: se modifica la visita original." % linea.id
        if linea.route_id.delivery_number_id != reparto:
            return linea, "La visita %s no pertenece al reparto %s." % (
                linea.id, reparto.location_id.aguas_idreparto,
            )
        if not linea.visit_date_hour:
            return linea, "La visita %s no tiene una visita registrada." % linea.id
        if linea.route_id.state != "in_progress":
            return linea, "El recorrido de la visita %s no esta en progreso." % linea.id
        return linea, self._check_visit_documents(linea)

    def _check_visit_documents(self, linea):
        """Error si algun documento de la visita ya no se puede modificar, o
        False. La venta con factura o confirmada y los remitos que ya no estan
        en borrador (confirmados, asignados o validados) se rechazan: solo se
        reemplaza lo que sigue en borrador. Los cancelados se ignoran."""
        order = linea.sale_order_id
        if order.invoice_ids.filtered(lambda invoice: invoice.state != "cancel"):
            return "El pedido %s tiene factura." % order.name
        if order and order.state not in EDITABLE_SALE_STATES:
            return "El pedido %s ya esta confirmado." % order.name
        pickings = order.picking_ids
        for field in VISIT_PICKING_FIELDS:
            pickings |= linea[field]
        not_draft = pickings.filtered(lambda picking: picking.state not in EDITABLE_PICKING_STATES)
        if not_draft:
            return "Los remitos %s ya no estan en borrador." % ", ".join(not_draft.mapped("name"))
        return False
