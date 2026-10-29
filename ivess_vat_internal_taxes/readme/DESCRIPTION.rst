Los reportes Contabilidad > Reportes > IVA > Sale VAT y Purchase VAT
(``sale.vat.wizard`` y ``purchase.vat.wizard``) de ``l10n_ar_eynes`` dejan los
impuestos internos fijos en 0, por lo que no aparecen en ninguna columna ni en
el total y los reportes no coinciden con el Subdiario de IVA.

Este módulo calcula los impuestos internos (impuestos con grupo de tipo
"internals") de facturas y notas de crédito del período, con el mismo criterio
de comprobantes que el resto de cada reporte, y los pasa al informe. No
modifica ``l10n_ar_eynes``.
