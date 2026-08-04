# BBVA Payment Order Export

Wizard que genera el archivo TXT posicional del servicio "Pago a
Proveedores" de BBVA. Implementados los registros 010 (cabecera), 020 (orden
de pago), 090 (proveedor beneficiario) y 095 (pie); el registro 025
(una orden pagada con más de un cheque/Echeq) todavía no está implementado.

Ver [`docs/ANALISIS_Y_DISENO.md`](docs/ANALISIS_Y_DISENO.md) para el análisis
técnico completo, la arquitectura propuesta y los puntos pendientes de
definición.

Material de referencia en `docs/`:

- `matriz_campos_bbva.csv` — los 128 campos del TXT BBVA (registros
  010/020/090/095), extraídos de la hoja `Matriz_campos` del Excel del
  cliente.
- `Analisis_campos_TXT_BBVA_JUMI_obligatoriedad.xlsx` — Excel original.
- `JUMI_OP_ECHEQS_2026-06-23.txt` — archivo real de ejemplo (2 Echeqs
  simples, sin casos de registro 025).
