{
    "name": "Ivess SICORE Split",
    "version": "19.0.0.0.1",
    "summary": "Ajustes al reporte SICORE: separador decimal, archivos "
    "separados IVA/Ganancias y código AFIP configurable en la percepción",
    "description": """
        T16639.

        - El separador decimal de los montos pasa de coma a punto.
        - Las retenciones de IVA y de Ganancias se exportan en archivos
          separados (antes salían mezcladas en el mismo archivo).
        - Se agrega el campo "SICORE Tax Code" en la percepción
          (Contabilidad > Configuración > Impuestos), para no depender de
          buscar el código por el diario vinculado.
        - El campo "Código de retención AFIP" del diario solo se muestra
          para diarios de tipo Retentions/Perceptions.
        - Se corrige el layout del archivo (comparado contra el archivo de
          referencia del cliente):
          - Importe total, base de cálculo e importe de retención/percepción
            van alineados a izquierda (antes a derecha).
          - Número de comprobante y CUIT del retenido/percibido van
            alineados a izquierda, sin ceros de relleno.
          - Porcentaje de exclusión y número de certificado propio van en
            blanco cuando no aplican (antes salían en "0.00" o en ceros).
          - El archivo local ahora completa 198 caracteres por línea
            (relleno con espacios), igual que el de exterior.
          - Código de condición del sujeto percibido (percepciones de
            IVA, régimen 602): "13" fijo, verificado contra el archivo
            real del cliente.
          - Número de comprobante de percepciones: se arma como punto de
            venta (5 dígitos) + número (8 dígitos) por separado, en vez
            de sacarle los caracteres no numéricos al nombre completo de
            la factura (pisaba el padding del punto de venta).
          - Número de comprobante de retenciones: se completa a 13
            dígitos con ceros a la izquierda (antes salía el número
            crudo de la Orden de Pago, sin padding, ej. "48").
          - Base de cálculo: a diferencia del resto de los importes, se
            omite el punto decimal y los centavos cuando el monto es
            entero (verificado contra 360 líneas reales del cliente:
            138 sin punto, exactamente las que dan centavos = 00).
          - Fix: "codigo_regimen" rompía con ValueError ("is defined as
            a integer but the value is not of that type") cuando el
            fallback caía en concept_id.code, un Char libre no
            necesariamente numérico (ej. "RG830") - ahora se queda solo
            con los dígitos, tanto en retenciones como en percepciones.

        T16863.

        - Fix: AFIP rechazaba el archivo de retenciones de Ganancias
          ("combinación régimen 78/94 + operación 1 + condición 13 no
          es válida" - 78/94 son régimenes de Ganancias/RG 830). El
          "13" fijo de T16639 solo corresponde a percepciones de IVA
          (régimen 602) - en retenciones de Ganancias la condición
          vuelve a tomarse de la situación del proveedor vía el mapeo
          de posición fiscal en sicore.fiscal.position (método original
          de l10n_ar_eynes, default "01" Inscripto si no está mapeada).
          Percepciones de IVA y retenciones de IVA se mantienen en
          "13" fijo (sin cambios, no mencionadas en esta tarea).
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [
        "views/account_tax_views.xml",
        "views/account_journal_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
