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
          - Código de condición del sujeto retenido/percibido: pasa de
            "01"/mapeo por partner (sin base real para retenciones,
            heredado del original) a "13" fijo, tanto para retenciones
            (IVA y Ganancias) como para percepciones.
          - Número de comprobante de percepciones: se arma como punto de
            venta (5 dígitos) + número (8 dígitos) por separado, en vez
            de sacarle los caracteres no numéricos al nombre completo de
            la factura (pisaba el padding del punto de venta).
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
