import logging
import time
from collections import defaultdict

from psycopg2 import errors as pg_errors

from odoo import models
from odoo.tools import SQL


_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _increase_rank(self, field, n=1):
        """En los asientos del Cierre Mensual los rangos de cliente/proveedor
        se suman con un único UPDATE por campo en lugar de una escritura por
        contacto (cada una recorre las validaciones de todos los módulos).

        El resultado es el mismo que el de account: los contactos sin rango se
        asignan en el momento (así quedan como cliente/proveedor) y a los que
        ya tienen se les suma después del commit. Los que además necesitan
        que se les asigne un código de cliente siguen yendo por escritura.
        """
        if not self.env.context.get("ivess_summary_close") or field not in (
            "customer_rank",
            "supplier_rank",
        ):
            return super()._increase_rank(field, n)

        postcommit = self.env.cr.postcommit
        key = f"ivess_accounting_summary.increase_rank.{field}"
        data = postcommit.data.setdefault(key, defaultdict(int))
        already_registered = bool(data)
        immediate = self.browse()
        for record in self.sudo():
            needs_code = (
                field == "customer_rank"
                and "customer_code" in record._fields
                and not record.customer_code
            )
            if record[field] and record.id and not needs_code:
                data[record.id] += n
            else:
                immediate |= record
        if immediate:
            super(ResPartner, immediate)._increase_rank(field, n)
        if already_registered or not data:
            return

        registry = self.env.registry
        table = self._table

        @postcommit.add
        def increase_summary_partner_rank():
            # Ordenado por id para que dos cierres a la vez no se bloqueen
            # entre sí; si igual choca con otra escritura se repite.
            pending = sorted(data.items())
            data.clear()
            query = SQL(
                "UPDATE %(table)s p SET %(field)s = p.%(field)s + v.n "
                "FROM (VALUES %(values)s) AS v(id, n) WHERE p.id = v.id",
                table=SQL.identifier(table),
                field=SQL.identifier(field),
                values=SQL(", ").join(
                    SQL("(%s, %s)", partner_id, count) for partner_id, count in pending
                ),
            )
            for attempt in range(5):
                try:
                    with registry.cursor() as cr:
                        cr.execute(query)
                    return
                except (pg_errors.SerializationFailure, pg_errors.DeadlockDetected):
                    time.sleep(0.2 * (attempt + 1))
            _logger.error("No se pudieron actualizar los rangos de contactos del cierre")
