import logging

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AguasFCIntake(models.AbstractModel):
    _name = "aguas.fc.intake"
    _description = "Procesador de entrada de equipos desde Aguas FC"

    @api.model
    def process_entrada(self, idreparto, equipos, fecha, tecnico, usuario):
        self = self.with_user(SUPERUSER_ID)
        src_location = self.env["stock.location"].search(
            [("aguas_idreparto", "=", str(idreparto))], limit=1
        )
        if not src_location:
            return {
                "success": False,
                "error": f"No existe ubicación para idreparto={idreparto}",
            }

        company = src_location.company_id
        taller_location = company.aguas_fc_taller_location_id
        picking_type = company.aguas_fc_picking_type_id
        product = company.aguas_fc_product_id

        if not taller_location:
            raise UserError(
                f"No está configurada la ubicación Taller FC en la empresa {company.name}."
            )
        if not picking_type:
            raise UserError(
                f"No está configurado el tipo de operación Aguas FC en la empresa {company.name}."
            )
        if not product:
            raise UserError(
                f"No está configurado el producto Equipo FC en la empresa {company.name}."
            )

        lots = []
        for serial in equipos:
            lot = self.env["stock.lot"].search(
                [
                    ("name", "=", serial),
                    ("product_id", "=", product.id),
                ],
                limit=1,
            )
            if not lot:
                lot = (
                    self.env["stock.lot"]
                    .with_company(company)
                    .create(
                        {
                            "name": serial,
                            "product_id": product.id,
                            "company_id": company.id,
                        }
                    )
                )
            lots.append(lot)

        picking = (
            self.env["stock.picking"]
            .with_company(company)
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": src_location.id,
                    "location_dest_id": taller_location.id,
                    "origin": f"AGUAS-{idreparto}-{fecha}",
                    "company_id": company.id,
                }
            )
        )

        move = (
            self.env["stock.move"]
            .with_company(company)
            .create(
                {
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_qty": len(lots),
                    "product_uom": product.uom_id.id,
                    "location_id": src_location.id,
                    "location_dest_id": taller_location.id,
                    "company_id": company.id,
                }
            )
        )

        # Confirmar antes de crear las move lines para que _action_confirm()
        # dispare _create_quality_checks() con el picking en estado draft.
        picking.action_confirm()

        for lot in lots:
            self.env["stock.move.line"].with_company(company).create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "quantity": 1,
                    "location_id": src_location.id,
                    "location_dest_id": taller_location.id,
                    "company_id": company.id,
                }
            )

        picking.with_context(
            skip_sanity_check=True,
            picking_ids_not_to_backorder=picking.ids,
        ).button_validate()

        _logger.info(
            "Aguas FC: picking %s creado y validado. Reparto=%s, seriales=%s",
            picking.name,
            idreparto,
            [l.name for l in lots],
        )

        return {
            "success": True,
            "picking_id": picking.id,
            "picking_name": picking.name,
            "seriales_procesados": len(lots),
        }

    # ------------------------------------------------------------------
    # Corrección de un ingreso ya registrado
    # ------------------------------------------------------------------
    @api.model
    def process_actualizacion(
        self, equipos, picking_id=None, idreparto=None, fecha=None
    ):
        self = self.with_user(SUPERUSER_ID)

        nuevas = {(s or "").strip() for s in (equipos or []) if (s or "").strip()}
        if not nuevas:
            return {
                "success": False,
                "error": "Para anular un ingreso completo, usar la ruta de anulación",
            }

        picking = self._localizar_ingreso(picking_id, idreparto, fecha)
        if not picking:
            referencia = picking_id or f"idreparto={idreparto}, fecha={fecha}"
            return {
                "success": False,
                "error": f"No se encontró el ingreso original ({referencia})",
            }

        company = picking.company_id
        src_location = picking.location_id
        taller_location = company.aguas_fc_taller_location_id
        product = company.aguas_fc_product_id

        if not taller_location:
            raise UserError(
                f"No está configurada la ubicación Taller FC en la empresa {company.name}."
            )
        if not product:
            raise UserError(
                f"No está configurado el producto Equipo FC en la empresa {company.name}."
            )

        current_lots = self._lotes_actuales_ingreso(
            picking, company, src_location, taller_location, product
        )
        actuales = set(current_lots)
        agregadas = nuevas - actuales
        quitadas = actuales - nuevas
        sin_cambio = nuevas & actuales

        if not agregadas and not quitadas:
            return {
                "success": True,
                "picking_id": picking.id,
                "agregados": [],
                "quitados": [],
                "sin_cambio": sorted(sin_cambio),
            }

        # Validar todo antes de mover nada: el pedido es atómico.
        error = self._validar_quitadas(quitadas, current_lots, taller_location)
        if error:
            return {"success": False, "error": error}

        lots_agregadas, advertencias = self._resolver_agregadas(
            agregadas, product, company, src_location
        )

        mensajes_chatter = self._aplicar_correccion(
            company,
            src_location,
            taller_location,
            product,
            picking.origin,
            lots_agregadas,
            agregadas,
            quitadas,
            current_lots,
        )
        picking.message_post(
            body="Corrección de ingreso Loop: " + "; ".join(mensajes_chatter) + "."
        )

        resultado = {
            "success": True,
            "picking_id": picking.id,
            "agregados": sorted(agregadas),
            "quitados": sorted(quitadas),
            "sin_cambio": sorted(sin_cambio),
        }
        if advertencias:
            resultado["advertencias"] = advertencias
        return resultado

    def _localizar_ingreso(self, picking_id, idreparto, fecha):
        if picking_id:
            return self.env["stock.picking"].browse(picking_id).exists()
        origin = f"AGUAS-{idreparto}-{fecha}"
        return self.env["stock.picking"].search([("origin", "=", origin)], limit=1)

    def _lotes_actuales_ingreso(
        self, picking, company, src_location, taller_location, product
    ):
        """Series que hoy están "en este ingreso": el picking original más todas
        las correcciones previas ya validadas, con el mismo origin. No alcanza
        con mirar solo el picking original porque una corrección previa puede
        haber sumado o sacado series."""
        related = self.env["stock.picking"].search(
            [
                ("origin", "=", picking.origin),
                ("company_id", "=", company.id),
                ("state", "=", "done"),
            ]
        )

        current_lots = {}
        for rel in related.sorted("create_date"):
            move_lines = rel.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.product_id == product
            )
            for move_line in move_lines:
                if move_line.location_dest_id == taller_location:
                    current_lots[move_line.lot_id.name] = move_line.lot_id
                elif move_line.location_dest_id == src_location:
                    current_lots.pop(move_line.lot_id.name, None)
        return current_lots

    def _validar_quitadas(self, quitadas, current_lots, taller_location):
        """Devuelve un mensaje de error si alguna serie a quitar no puede
        salir del taller (tiene una reparación activa, o ya no está ahí)."""
        RepairOrder = self.env["repair.order"]
        Quant = self.env["stock.quant"]
        for serie in quitadas:
            lot = current_lots[serie]
            repair = RepairOrder.search(
                [
                    ("lot_id", "=", lot.id),
                    ("state", "not in", ["cancel", "done"]),
                ],
                limit=1,
            )
            if repair:
                return (
                    f"La serie {serie} tiene la orden de reparación {repair.name} "
                    f"activa; corregir desde Odoo."
                )
            en_taller = Quant.search(
                [
                    ("lot_id", "=", lot.id),
                    ("location_id", "=", taller_location.id),
                    ("quantity", ">", 0),
                ],
                limit=1,
            )
            if not en_taller:
                otro = Quant.search(
                    [
                        ("lot_id", "=", lot.id),
                        ("quantity", ">", 0),
                    ],
                    limit=1,
                )
                ubicacion = (
                    otro.location_id.complete_name
                    if otro
                    else "ninguna ubicación con stock"
                )
                return f"La serie {serie} no está en el taller, está en {ubicacion}."
        return None

    def _resolver_agregadas(self, agregadas, product, company, src_location):
        """Busca o crea el lote de cada serie nueva. Devuelve además una
        advertencia (no bloqueante) por cada una que no estaba físicamente en
        la ubicación del reparto."""
        Quant = self.env["stock.quant"]
        advertencias = []
        lots_agregadas = []
        for serie in agregadas:
            lot = self.env["stock.lot"].search(
                [
                    ("name", "=", serie),
                    ("product_id", "=", product.id),
                ],
                limit=1,
            )
            if not lot:
                lot = (
                    self.env["stock.lot"]
                    .with_company(company)
                    .create(
                        {
                            "name": serie,
                            "product_id": product.id,
                            "company_id": company.id,
                        }
                    )
                )
            lots_agregadas.append(lot)
            en_reparto = Quant.search(
                [
                    ("lot_id", "=", lot.id),
                    ("location_id", "=", src_location.id),
                    ("quantity", ">", 0),
                ],
                limit=1,
            )
            if not en_reparto:
                advertencias.append(
                    f"La serie {serie} no estaba en la ubicación del reparto"
                )
        return lots_agregadas, advertencias

    def _aplicar_correccion(
        self,
        company,
        src_location,
        taller_location,
        product,
        origin,
        lots_agregadas,
        agregadas,
        quitadas,
        current_lots,
    ):
        mensajes_chatter = []

        if lots_agregadas:
            self._crear_traslado_correccion(
                company=company,
                src_location=src_location,
                dest_location=taller_location,
                product=product,
                lots=lots_agregadas,
                origin=origin,
                picking_type=company.aguas_fc_picking_type_id,
            )
            mensajes_chatter.append(f"entraron: {', '.join(sorted(agregadas))}")

        if quitadas:
            # Mismo tipo de operación que el ingreso (no uno de otro almacén
            # elegido a ciegas: con varios almacenes por compañía, cualquier
            # tipo "interno" que no sea el de este numera el traslado con el
            # prefijo de secuencia de otro almacén). El efecto no deseado de
            # reusarlo -- que se cree una reparación nueva para un equipo que
            # está saliendo del taller -- se corta con skip_auto_repair.
            self._crear_traslado_correccion(
                company=company,
                src_location=taller_location,
                dest_location=src_location,
                product=product,
                lots=[current_lots[s] for s in quitadas],
                origin=origin,
                picking_type=company.aguas_fc_picking_type_id,
                skip_auto_repair=True,
            )
            mensajes_chatter.append(f"salieron: {', '.join(sorted(quitadas))}")

        return mensajes_chatter

    def _crear_traslado_correccion(
        self,
        company,
        src_location,
        dest_location,
        product,
        lots,
        origin,
        picking_type,
        skip_auto_repair=False,
    ):
        picking = (
            self.env["stock.picking"]
            .with_company(company)
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": src_location.id,
                    "location_dest_id": dest_location.id,
                    "origin": origin,
                    "company_id": company.id,
                }
            )
        )

        move = (
            self.env["stock.move"]
            .with_company(company)
            .create(
                {
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_qty": len(lots),
                    "product_uom": product.uom_id.id,
                    "location_id": src_location.id,
                    "location_dest_id": dest_location.id,
                    "company_id": company.id,
                }
            )
        )

        picking.action_confirm()

        for lot in lots:
            self.env["stock.move.line"].with_company(company).create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "quantity": 1,
                    "location_id": src_location.id,
                    "location_dest_id": dest_location.id,
                    "company_id": company.id,
                }
            )

        picking.with_context(
            skip_sanity_check=True,
            picking_ids_not_to_backorder=picking.ids,
            skip_frio_calor_auto_repair=skip_auto_repair,
        ).button_validate()

        _logger.info(
            "Aguas FC: corrección %s creada y validada. Reparto=%s -> %s, seriales=%s",
            picking.name,
            src_location.complete_name,
            dest_location.complete_name,
            [lot.name for lot in lots],
        )

        return picking
