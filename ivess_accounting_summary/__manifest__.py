{
    "name": "Ivess Accounting Summary",
    "version": "19.0.0.0.0",
    "summary": "Contabilidad Resumida (Diarios Espejo) y Foliación Legal",
    "description": """
        Contabilidad Resumida (Diarios Espejo). Los diarios operativos
        (Ventas/Compras/Pagos) registran el detalle transaccional pero no
        se imprimen en el libro diario legal; un Diario de Refundición
        (Legal) concentra asientos resumen mensuales, que son los únicos
        que se exportan para la rúbrica.

        - Fase 1 - Modelos y campos base:
          - account.account: x_summarize_on_report (colapsar la cuenta en
            la impresión del libro legal) y x_legal_debt_account_id
            (mapeo de la cuenta operativa de deudores/acreedores a su
            equivalente legal).
          - account.journal: x_is_legal_journal (marca los diarios de
            Refundición/Cierre de Ejercicio sujetos a foliación legal).
          - account.move: x_folio_legal, x_is_summary_entry y
            x_closed_by_summary_move_id.
          - account.move.line: x_origin_document_id y x_summary_move_id
            (trazabilidad y anti-duplicación del cierre mensual).

        - Fase 2 - Asistente de Cierre Mensual (Contabilidad > Cierre):
          dado un período y los diarios operativos a resumir, en una
          única transacción: sumariza resultados e impuestos y genera el
          asiento inverso (neteo) en cada diario operativo; concilia ese
          neteo contra el saldo pendiente de los comprobantes originales
          (quedan "Cerrados por Resumen"); y genera un único asiento en
          el Diario Legal con los totales por cuenta/impuesto más una
          línea de deuda por cada comprobante abierto, trazable a su
          origen.

        - Fase 3 - QWeb y Foliación Legal:
          - Renumeración de Folio Legal (Contabilidad > Cierre):
            recalcula x_folio_legal en orden de fecha, sin huecos, para
            los diarios marcados x_is_legal_journal.
          - Impresión del Libro Diario (PDF): las cuentas marcadas
            x_summarize_on_report se colapsan en un único monto
            totalizador "(Resumen Global)", ocultando el desglose por
            partner sin alterar el detalle en pantalla ni en Excel.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": ["account", "account_reports"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_account_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "wizard/account_summary_closing_wizard_views.xml",
        "wizard/legal_folio_renumber_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
