# BBVA Payment Order Export — Análisis y diseño

Módulo aún sin código (`installable: False` en `__manifest__.py`). Este documento
condensa el análisis técnico y las decisiones de diseño discutidas antes de
empezar a programar, para que una sesión futura (humana o con IA) pueda
retomarlo sin perder contexto.

## 1. Contexto y objetivo

Desarrollar en Odoo 19 Enterprise un exportador de órdenes de pago para el
servicio "Pago a Proveedores" de BBVA/Banco Francés: un archivo TXT posicional
de **850 caracteres por línea, sin separadores entre campos**, codificación
ANSI/ASCII, saltos de línea CR/LF.

Registros posibles: `010` (cabecera), `020` (orden de pago), `025` (detalle
cuando una orden se divide en varios Echeqs), `090` (proveedor beneficiario),
`095` (totales/cierre).

**Alcance de esta primera etapa**: Echeqs simples y múltiples, registros
`010`, `020`, `025`, `090`, `095`. Facturas y retenciones quedan para una
etapa posterior, a confirmar con el cliente y el banco.

## 2. Material de referencia (en `docs/`)

- `Analisis_campos_TXT_BBVA_JUMI_obligatoriedad.xlsx` — Excel original del
  cliente, hoja `Matriz_campos` es la relevante para el desarrollo (128
  campos). Las hojas `L1_010`...`L6_095`, `Resumen` y `Registros_crudos` son
  el desglose campo-por-campo del archivo de ejemplo, ya usadas para validar
  la matriz.
- `matriz_campos_bbva.csv` — la hoja `Matriz_campos` exportada tal cual a CSV
  (128 filas, columnas: `Registro, Campo, Observaciones, Inicio, Longitud,
  Ejemplo JUMI, Clasificación, Origen sugerido en Odoo, Existe en Odoo ?,
  Nombre campo, Nombre tecnico, Modelo, ¿Nuevo campo?, Definición / forma de
  completar`). Es la fuente de verdad para armar los dicts de `FixedWidth`
  de los registros **010, 020, 090, 095** (el 025 no tiene filas acá, ver
  más abajo).
- **`BBVA DDRR Pago a Proveedores.docx.pdf`** — **especificación oficial del
  banco** ("FNC-Pago a Proveedores 05-2019", 59 páginas). Estaba en la
  carpeta pero no había sido leída/citada en este análisis. Cubre el diseño
  completo de los 10 tipos de registro (010/020/025/030/040/060/070/080/
  090/095), reglas de validación de importes y fechas, tabla de provincias,
  y el procedimiento operativo de envío/firma/devolución por Net Cash. Ver
  **Apéndice A** al final de este documento para el volcado completo,
  campo por campo.
- `JUMI_OP_ECHEQS_2026-06-23.txt` — archivo real de ejemplo (6 líneas: 010,
  020, 090, 020, 090, 095; sin ningún caso de registro 025). Ya validado:
  cada línea tiene exactamente 850 caracteres, sin huecos ni solapamientos
  entre campos, y los totales/cantidades del registro 095 cierran contra los
  dos registros 020 reales.
- **`IMPA_OP_ECHEQS_2026-06-23.txt`** y **`LUFRAN_OP_ECHEQS_2026-06-23.txt`**
  — dos archivos reales adicionales, tampoco citados hasta ahora en este
  análisis. **Ambos sí tienen casos de registro 025** (IMPA: una orden con 4
  Echeqs; LUFRAN: una orden con 7), que es justo el caso que faltaba
  validar (ver punto abierto #2, ahora resuelto).

## 3. Qué ya existe en este Odoo (reusar, no reinventar)

| Necesidad | Ya existe como |
|---|---|
| Órdenes de pago | `account.payment.order` — modelo **propio** de `l10n_ar_eynes` (no es el OCA `account_payment_order`). Campos clave: `number`, `state`, `company_id`, `journal_id` (de acá sale la cuenta de débito), `date`/`date_effective`/`date_due`, `amount`, `currency_id`, `type` (payment/receipt) |
| Relación OP ↔ Echeqs | `account.payment.order.issued_check_ids` (One2many a `account.check`) |
| Distinguir Echeq de cheque físico | `account.check.checkbook_format` (`physical` / `echeq`) |
| Otros campos de `account.check` | `number`, `amount`, `issue_date`, `payment_date`, `currency_id`, `journal_id`, `journal_bank_id` (related a `journal_id.bank_account_id`), `bank_id`, `checkbook_id` (talonario, Many2one a `account.payment.method.line`), `receiving_partner_id`, `payment_order_id`, `issued_check_state` |
| Motor de armado de línea posicional | Clase `FixedWidth` + `moneyfmt()` en `l10n_ar_eynes/l10n_ar_eynes/utils/sicore_fixed_width.py`. Recibe un dict de spec por campo (`start_pos`, `length`/`end_pos`, `type` string/integer/decimal/numeric, `alignment`, `padding`, `required`, `default`, `value` fijo) y arma/valida la línea completa. Ya la usan los exportadores de SICORE/SIFERE/ARCIBA/ARBA — **reusar tal cual, no reescribir el motor**. |
| Patrón de wizard + selección múltiple + validación | `account_payment_order_mass_email` — filtra por estado, informa qué OPs se omiten |
| Patrón de trazabilidad archivo↔lote | `arba.generated.files` / `libroiva.generated.files`: modelo simple (`code`, `company_id`, fechas, `attachment_id` M2O a `ir.attachment`) — clonable para el lote BBVA |
| CBU / CUIT de la empresa | `res.company.cbu`, `res.company.cuit`, `res.partner.vat` |
| Datos del proveedor beneficiario | `res.partner` estándar (vat, email, dirección) |

Ejemplo de wizard existente a tomar como plantilla de patrón (armado de línea +
adjunto + registro de trazabilidad):
`l10n_ar_eynes/l10n_ar_eynes/wizard/arba_retention_exporter.py`.

### 3.1 Cardinalidad: qué modelo genera cada tipo de registro

Agrupando la columna `Modelo` de `matriz_campos_bbva.csv` por `Registro`, sale
la vista de cardinalidad — cuántas líneas de cada tipo emite el exportador y
de qué modelo salen — que no es evidente mirando la matriz campo por campo:

| Registro | Modelo "raíz" (define cuántas líneas salen) | Se arma con | Cardinalidad |
|---|---|---|---|
| **`010`** cabecera | Ninguno — es agregado de config + lote | `res.company` (CUIT), `account.journal` (moneda/cuenta débito), `account.payment.mode.line` (forma pago), + `IMPORTE_TOTAL`/`FECHA_EMISION` calculados sobre el recordset completo de OPs seleccionadas | **1 línea siempre** (una por archivo exportado) |
| **`020`** orden de pago | **`account.payment.order`** | `account.payment.order.retention.line` (certificados de retención — fuera de alcance), `account.payment.mode.line` (fechas), `account.check` (nro. cheque) | **1 línea por cada OP** seleccionada en el wizard |
| **`025`** detalle multi-Echeq | **`account.check`** (vía `account.payment.order.issued_check_ids`) | — | **1 línea por cada Echeq adicional**, cuando una OP tiene más de un cheque asociado (0 líneas si la OP tiene un solo Echeq) — coincide con que el archivo de ejemplo no tiene ninguna |
| **`090`** proveedor beneficiario | **`res.partner`** (el beneficiario de la OP) | referencia de vuelta a `account.payment.order` vía `PRO_NRO_ORD` | **1 línea por cada OP** (mismo bucle que `020`, va inmediatamente después de su `020`) |
| **`095`** totales/cierre | Ninguno — calculado | `res.company` (CUIT) + conteos/sumas sobre las mismas OPs de `010` | **1 línea siempre** (una por archivo) |

Conclusión para el diseño del exportador: hay **un solo bucle real**, sobre
el recordset de `account.payment.order` seleccionado en el wizard, que por
cada OP emite un `020` + su `090` (+ los `025` que correspondan según
cantidad de Echeqs). El `010` y el `095` se calculan una sola vez sobre todo
el lote — no hay un modelo Odoo que represente "el archivo completo"; esa
responsabilidad es del wizard/motor de generación, no de un modelo
persistido.

## 4. Resumen del análisis de campos (`matriz_campos_bbva.csv`)

128 campos totales: 29 en el registro 010, 33 en el 020, 57 en el 090, 9 en el
095. **El registro 025 tiene 0 filas en la matriz** — ver sección de puntos
abiertos.

Validación cruzada contra el archivo real: por cada tipo de registro, la
posición final del `FILLER_FINAL` cierra exactamente en 850 (010: fin en 850
con filler desde 153/long 698; 020: filler desde 345/long 506; 090: filler
desde 633/long 218; 095: filler desde 61/long 790). Sin huecos ni
solapamientos.

Clasificación de los 128 campos por columna "Existe en Odoo ?":

| Valor | Cantidad |
|---|---|
| Sí | 39 |
| No | 45 |
| ? (a definir) | 32 |
| Tal vez | 1 |
| Posiblemente | 1 |
| (vacío) | 10 |

Modelos ya identificados en la matriz para los 39 campos que sí existen:
`res.partner` (17), `account.payment.order` (10), `account.payment.mode.line`
(3), `account.payment.order.retention.line` (2), `account.journal` (1),
`account.move.line` (1), `account.check` (1), sin modelo asignado (4).

Buena parte de los 128 campos son constantes fijas de BBVA (`IDENT_REGISTRO`,
`TIPO_REG`, `ENTIDAD=0017`, fillers de espacios) o valores calculados
(secuencias, totales, cantidades de registros) — no requieren ningún campo en
Odoo, se generan en el momento de exportar.

### 4.1 Campos nuevos confirmados (columna "¿Nuevo campo?" = "Sí o parametrizable")

Los 5 están en el registro 010 (cabecera, cuenta de débito):

| Campo | Posición | Longitud | Existe hoy | Definición |
|---|---|---|---|---|
| `SUC_CTA_DEBITO` | 78 | 4 | No | Sucursal de radicación de la cuenta de débito, la informa BBVA |
| `DV_CTA_DEBITO` | 82 | 2 | No | Dígito verificador de la cuenta, lo informa BBVA |
| `TIPO_CTA_DEBITO` | 84 | 2 | Tal vez | **Resuelto por el PDF (pág. 15/16): "Tipo de cuenta débito. Debe completarse con 01".** Es un valor fijo del formato, no depende del contrato — no hace falta confirmarlo con BBVA, solo hardcodearlo |
| `MONEDA_CTA_DEBITO` | 86 | 1 | Sí (marcado inconsistente en la matriz: dice "Sí" y modelo `account.move.line`, pero igual está tildado como nuevo — revisar) | El PDF confirma que también es fijo: "Divisa de la cuenta débito. Debe completarse con 0 (cero)" |
| `NRO_CTA_DEBITO` | 87 | 7 | Sí (misma inconsistencia que arriba) | Número de cuenta de débito, 7 posiciones, lo informa BBVA |

El PDF (pág. 10) además trae la lista taxativa de qué datos del registro 010
hay que pedirle al implementador de BBVA antes de poder emitir pagos
("Set de datos obligatorio"): `nro-cuit-empresa`, `suc-cta-débito`,
`dv-cta-débito`, `tipo-cta-débito`, `moneda-cta-débito`, `nro-cta-débito`,
`contrato-prov`. De estos, `tipo-cta-débito` y `moneda-cta-débito` ya están
resueltos arriba (son fijos); los otros 5 sí son específicos de la
contratación del cliente con el banco y hay que solicitarlos.

Más los campos que surgieron del análisis conversacional (no están como fila
individual en el Excel porque son de configuración/proceso, no de contenido
del TXT):

- **Modalidad BBVA del Echeq** — no hay ninguna clasificación BBVA-específica
  en `account.check` (solo el genérico `checkbook_format`).
- **Contrato de Pago a Proveedores BBVA** — sin precedente en
  `res_config_settings.py` de ningún módulo bancario existente.
- **Secuencia/número de minuta o lote** — no hay `ir.sequence` reusable; los
  exportadores existentes arman el nombre de archivo con fecha+hash MD5, no
  con una secuencia numérica correlativa real.
- **Guard anti-doble-exportación** de una OP — no hay ningún precedente
  (`already_exported`, `export_state`, etc. no existen en el repo).

### 4.2 Campos "Existe en Odoo = ?" (32, a investigar más)

Mayoritariamente en el registro 090: domicilio de entrega alternativo
(`PRO_*_ENTREGA`), teléfonos (`PRO_TELEF_*`), autorizantes de cheque físico
(`PRO_AUTORIZA_*`). La propia matriz los marca como "NO OBLIGATORIO PARA
ECHEQ" / "OPCIONAL" / "CONDICIONAL PARA CHEQUE FÍSICO" — **no son bloqueantes
para el alcance actual** (Echeq simple/múltiple). Revisar uno por uno recién
al implementar el registro 090.

### 4.3 Estructura de línea: tipo de registro y reglas de relleno

Cada línea de 850 caracteres arranca con dos campos técnicos fijos que
identifican qué contiene:

| Posición | Campo | Valor |
|---|---|---|
| 1-4 | `IDENT_REGISTRO` | Fijo `0306` en todas las líneas (constante técnica del formato BBVA, no varía por tipo de registro) |
| 5-7 | `TIPO_REG` | `010` / `020` / `025` / `090` / `095` — define el resto del layout de esa línea |

En el archivo de ejemplo (`JUMI_OP_ECHEQS_2026-06-23.txt`) el orden de líneas
fue:

```
010                       → cabecera (una sola vez, al inicio)
020                       → orden de pago #1
  090                     → proveedor beneficiario del pago #1
020                       → orden de pago #2
  090                     → proveedor beneficiario del pago #2
095                       → totales/cierre (una sola vez, al final)
```

Es decir, cada orden de pago (`020`) va seguida del/los `090` de su
proveedor. Cuando una orden se paga con más de un Echeq, ahí aparecería un
`025` entre el `020` y su(s) `090` — pendiente de especificar (punto abierto
#2).

**Reglas de relleno** (lo que hace `FixedWidth`/`moneyfmt()` de forma
automática a partir del `type` declarado en el dict de cada campo — no hay
que calcularlo a mano al programar):

- **Campo numérico** (secuencias, códigos, CUIT/CUIL, CBU, importes) → se
  completa con **ceros a la izquierda** hasta la longitud exacta. Ej.:
  `PRO_NRO_BENEF` (15 posiciones) con valor `5` → `000000000000005`.
- **Campo de texto** (razón social, calle, email) → se completa con
  **espacios a la derecha** hasta la longitud exacta. Ej.: `PRO_DENOMINA`
  (40 posiciones) con valor `Goldstein, Mario` → `Goldstein, Mario` + 24
  espacios.
- **Campo fijo/constante** (`IDENT_REGISTRO`, `TIPO_REG`, `ENTIDAD`,
  `PRO_CODPAIS=080`) → siempre el mismo valor, definido por el banco.
- **Campo no aplicable al alcance actual** (autorizantes de cheque físico,
  CBU y teléfonos para Echeq) → **igual debe estar presente**, relleno según
  su tipo (ceros si es numérico, espacios si es texto) — el layout es
  posicional rígido, no se pueden omitir campos ni correr posiciones aunque
  el dato no aplique.
- **`FILLER_FINAL`** de cada tipo de registro → espacios hasta cerrar
  exactamente en 850 caracteres + salto de línea CR/LF.

#### Ejemplo comentado: registro `090` (línea 3 del archivo real)

```
0306090CUIT00305378828710000022026062377914430000000000000051CUI20139802730Goldstein, Mario                          N0000000000000000000000000000000000000           General Guido 1455                                                 02080imprentageneralpaz@hotmail.com...00000000...00078811...
```

| Campo | Pos-Long | Valor | Relleno aplicado |
|---|---|---|---|
| `IDENT_REGISTRO` | 1-4 | `0306` | fijo |
| `TIPO_REG` | 5-7 | `090` | fijo |
| `TIPO_DOC_EMPRESA` | 8-11 | `CUIT` | fijo |
| `CUIT_EMPRESA` | 12-24 | `0030537882871` | numérico, ceros a la izq. (13) |
| `SECUENCIA` | 25-30 | `000002` | numérico, ceros a la izq. (6) |
| `PRO_NRO_ORD` | 31-45 | `202606237791443` | dato existente, ya ocupa 15 |
| `PRO_NRO_BENEF` | 46-60 | `000000000000005` | numérico, ceros a la izq. (15) — ver punto abierto #1 |
| `PRO_EST_BENEF` | 61 | `1` | fijo |
| `PRO_DOCTO_TIP` | 62-64 | `CUI` | código fijo |
| `PRO_DOCTO_NRO` | 65-75 | `20139802730` | numérico, CUIT proveedor (11) |
| `PRO_DENOMINA` | 76-115 | `Goldstein, Mario` + espacios | texto, espacios a la derecha (40) |
| `PRO_CATEGO` | 116-117 | (blanco) | no utilizado, espacios |
| `PRO_PERMIT_FINAN` | 118 | `N` | fijo para Echeq |
| `PRO_CUS_TIP/SUC/NRO` | 119-133 | `00`/`000`/`0000000000` | campo viejo sin uso, siempre ceros |
| `PRO_CBU_NRO` | 134-155 | ceros | Echeq no usa CBU |
| `PRO_CALLE` | 167-190 | `General Guido 1455` + espacios | texto, espacios a la derecha (24) |
| `PRO_CODPROV` / `PRO_CODPAIS` | 234-238 | `02` / `080` | código fijo (BA=02, Argentina=080) |
| `PRO_EMAIL` | 239-278 | email + espacios | texto, espacios a la derecha (40) |
| `PRO_AUTORIZA_DOC1/2/3` | 445/481/517 | `00000000` | cheque físico, no aplica a Echeq → ceros |
| `PRO_MINUTA` | 625-632 | `00078811` | numérico, debe coincidir con el mismo campo del `020` |
| `FILLER_FINAL` | 633-850 | espacios | relleno técnico hasta 850 |

## 5. Puntos abiertos — resolver antes (o durante) el desarrollo

1. **`PRO_NRO_BENEFICIARIO`** (registro 020, posición 31, longitud 15) y su
   par **`PRO_NRO_BENEF`** (registro 090, posición 46, longitud 15) —
   **parcialmente aclarado por el PDF**: la spec solo exige que sea
   "el número con el que identifica a su proveedor" y que coincida entre el
   020 y el 090 — el banco **no impone** si debe ser correlativo por archivo
   o un ID estable del proveedor, queda a criterio del cliente/implementación.
   Sigue siendo una decisión de diseño (no un bloqueo de spec): **definir si
   es correlativo por archivo o un identificador persistente por partner**
   antes de programar este campo.

2. ~~**Registro 025** (multi-Echeq) — la matriz tiene 0 filas para este
   registro...~~ **RESUELTO.** El PDF (pág. 23-24) trae el diseño completo
   del registro 025 (21 campos, ver Apéndice A). Además `IMPA_OP_ECHEQS...txt`
   y `LUFRAN_OP_ECHEQS...txt` (no analizados hasta ahora) sí traen casos
   reales de multi-Echeq (4 y 7 líneas `025` respectivamente). Crucé ambas
   fuentes campo por campo y coinciden exactamente (`NRO-MINUTA`, `IMPORTE`,
   `IPERMFIN`, `FECHA-PAGO`, `FORMA-PAGO=EC`, `DISPON-P`, `NRO-CHEQUE`).
   **Hallazgo adicional no documentado antes**: cuando una orden se paga con
   más de un instrumento, el registro **020 de esa orden** debe llevar
   `FORMA-PAGO = "MP"` y `DISPON-P = "9"` (en vez del código de instrumento
   real, que pasa a informarse en cada `025`) — confirmado por el PDF (pág.
   20-21) y verificado en los 3 archivos reales: las órdenes simples de JUMI/
   IMPA/LUFRAN tienen `FORMA-PAGO=EC, DISPON-P=1`, mientras que las 2 órdenes
   multi-Echeq (IMPA minuta `00000698`, LUFRAN minuta `00001679`) tienen
   `FORMA-PAGO=MP, DISPON-P=9`. Este detalle no estaba en ninguna versión
   anterior del análisis y es necesario para el motor de generación (el
   `020` no puede simplemente repetir el tipo de pago del primer Echeq).

3. Confirmar explícitamente con el cliente y el banco que los registros de
   facturas y retenciones (030/040/060/070/080) quedan fuera de esta primera
   etapa. El PDF sí trae el diseño completo de los 5 (ver Apéndice A), por si
   se decide adelantar alguno.

4. ~~**`TIPO_CTA_DEBITO`**: confirmar con BBVA...~~ **RESUELTO** — ver
   sección 4.1, es un valor fijo (`01`) según el PDF, no depende del contrato.

5. **Granularidad del mecanismo de anulación manual** (ver sección 7.5): ¿se
   anula solo el lote completo, o también OPs individuales dentro de un lote?
   Pendiente de definición del cliente — el PDF no tiene una funcionalidad de
   anulación de archivos ya enviados (una vez firmado y enviado por Net Cash,
   la única vía de "reversa" es el circuito de devoluciones del banco, ver
   Apéndice A.11), así que este mecanismo es 100% interno de Odoo (marcar
   OPs como no exportadas), no algo que dependa de una API del banco.

## 6. Arquitectura propuesta

### 6.1 Motor de generación

Reusar `FixedWidth` + `moneyfmt()` tal cual existen hoy. Un dict de config por
tipo de registro (010/020/025/090/095), siguiendo el mismo patrón que
`sicore_fixed_width_dicts.py` / `arba_fixed_width_dicts.py` de `l10n_ar_eynes`.
La posición/longitud/tipo de cada campo es el contrato fijo del banco —
conviene que viva en código versionado y testeado contra el archivo de
ejemplo real (`JUMI_OP_ECHEQS_2026-06-23.txt`), no como configuración de
runtime.

### 6.2 Mapeo de campos configurable (híbrido)

Se evaluaron tres enfoques:

1. Dicts 100% hardcodeados en Python (patrón actual de SICORE/ARBA) — simple,
   consistente con el resto del código, pero cualquier ajuste requiere deploy.
2. Todo configurable por UI (posición, longitud, fuente, formato) — máxima
   flexibilidad, pero sobre-ingeniería para un spec que define el banco y no
   cambia por capricho.
3. **Híbrido (elegido)**: posición/longitud/tipo quedan en el dict Python
   versionado (el contrato del banco). Lo que se vuelve configurable es **la
   fuente del valor**, para los campos que son simplemente "traer un campo de
   Odoo": un modelo `bbva.export.field.mapping` con `registro`, `campo_bbva`,
   `tipo` (fijo / campo Odoo / calculado), y si es "campo Odoo" un `field_path`
   (char, ej. `partner_id.vat`) resuelto con `record.mapped(path)` — mecanismo
   nativo de Odoo, no hay que inventar un intérprete propio. Los campos fijos
   (constantes del banco) y los calculados (totales, secuencias, cantidades)
   quedan en Python porque no son "mapeables", son lógica de generación.

Esta misma tabla de mapeo sirve de base para la vista de previsualización
(sección 6.3): permite mostrar de dónde salió cada valor.

### 6.3 Wizard de exportación (3 pasos)

1. **Selección + validación**: el usuario selecciona una o varias OPs
   (multi-select desde el list view, mismo patrón que
   `account_payment_order_mass_email`). El sistema valida:
   - Todas las OPs son de la misma compañía y misma cuenta bancaria
     (`journal_id`).
   - Ninguna fue exportada ya en un lote anterior (guard anti-duplicado).
   - Todos los campos obligatorios están completos (según la matriz).
   Si algo falla, se lista **por OP** qué falta, sin dejar avanzar hasta
   corregir o excluir esa OP de la selección.

2. **Previsualización**: se arma el archivo en memoria (sin generar el
   adjunto todavía) y se muestra en dos vistas:
   - **Tabular**: registro / posición / campo BBVA / valor resuelto / origen
     (fijo, campo Odoo, calculado) — para detectar campos vacíos o que no
     entran en el largo esperado.
   - **Texto plano monoespaciado**: el TXT tal cual va a salir, línea por
     línea.
   El usuario puede volver atrás, corregir un dato en Odoo, y recargar la
   previsualización sin haber generado nada todavía.

3. **Confirmación y descarga**: al confirmar (y solo en ese momento):
   - Se crea el registro de trazabilidad del lote.
   - Se cuelga el `ir.attachment` con el TXT real.
   - Se marcan las OPs incluidas como "exportadas a BBVA" (activa el guard
     anti-duplicado).
   - El navegador descarga el archivo.

### 6.4 Trazabilidad

Clon del patrón `arba.generated.files`: modelo de "lote generado" con fecha,
usuario, compañía, cantidad de OPs, importe total, y el `ir.attachment`
colgado. Smart button en `account.payment.order` ("Exportado a BBVA") que
lleva al lote correspondiente.

### 6.5 Anulación manual (no automática)

El guard anti-duplicado bloquea por defecto, pero **debe existir una salida
manual explícita** — nunca automática — para cuando el banco rechaza el
archivo (o una OP puntual).

- El lote tiene `state`: **Generado** / **Anulado**.
- Botón "Anular exportación", visible solo si el estado es "Generado",
  restringido a un grupo de seguridad más alto que el que usa el wizard
  normal (ej. "Tesorería - Supervisor").
- Pide un **motivo obligatorio** (texto) y queda registrado en el chatter
  (quién, cuándo, por qué).
- Libera el flag "exportada" de las OPs incluidas, para que vuelvan a estar
  disponibles en el wizard.
- El TXT ya generado **no se borra ni se sobrescribe** — el archivo que
  efectivamente se mandó al banco queda accesible para siempre, aunque el
  lote esté anulado.

**Pendiente de definir con el cliente** (ver punto abierto #5): si la anulación es
solo a nivel de lote completo (más simple, pero si falla 1 de 10 pagos hay que
re-exportar los 10) o también granular por OP individual dentro de un lote
(más seguro operativamente, algo más de desarrollo — requiere trackear estado
por OP, no solo por lote).

## 7. Flujo de usuario (UX)

### 7.1 Configuración inicial (una sola vez, admin/implementador)

- Menú "Contabilidad → Configuración → BBVA Pago a Proveedores" (o en Ajustes
  de compañía). Carga de sucursal/DV/tipo de cuenta/contrato BBVA (vinculados
  al `account.journal` de la cuenta de débito).
- Configuración de la secuencia de minuta/lote.
- Tabla de mapeo de campos (`bbva.export.field.mapping`) precargada por el
  desarrollo; el admin normalmente no la toca, pero queda editable ahí por si
  hace falta reapuntar el origen de un dato sin pedir deploy.

### 7.2 Uso diario (Tesorería / Cuentas a Pagar)

Ver selección → wizard (validación → previsualización → confirmación y
descarga) descripto en la sección 6.3.

### 7.3 Trazabilidad / histórico

Menú "Archivos BBVA generados": lista de lotes con fecha, usuario, cantidad
de OPs, importe total, TXT descargable de nuevo en cualquier momento, y
detalle de qué OPs incluyó cada lote.

### 7.4 Manejo de rechazos

Acción de anulación manual descripta en 6.5, con permiso restringido.

## 8. Próximos pasos para retomar el desarrollo

1. ~~Conseguir la especificación de registros de BBVA...~~ **Hecho** — está
   en `docs/BBVA DDRR Pago a Proveedores.docx.pdf`, volcada completa en el
   Apéndice A. El dict del registro `025` ya se puede armar directamente
   desde ahí (validado contra `IMPA_OP_ECHEQS...txt` / `LUFRAN_OP_ECHEQS...
   txt`).
2. Definir con el cliente el origen de `PRO_NRO_BENEFICIARIO` /
   `PRO_NRO_BENEF` (contador por lote vs. identificador estable del
   proveedor) — punto abierto #1, el banco no lo condiciona.
3. Definir la granularidad de la anulación manual (lote completo vs. OP
   individual) — punto abierto #5.
4. ~~Confirmar `TIPO_CTA_DEBITO` con BBVA...~~ **Hecho** — es fijo (`01`) y
   `MONEDA_CTA_DEBITO` también es fijo (`0`), ambos confirmados por el PDF
   (sección 4.1). Sigue pendiente pedirle al implementador de BBVA los 5
   datos de contratación que sí son variables (`nro-cuit-empresa`,
   `suc-cta-débito`, `dv-cta-débito`, `nro-cta-débito`, `contrato-prov`).
5. Con los puntos 2 y 3 cerrados (los otros dos ya no bloquean): armar los
   dicts de `FixedWidth` para 010/020/025/090/095 a partir de
   `matriz_campos_bbva.csv` + Apéndice A, el modelo
   `bbva.export.field.mapping`, el wizard de 3 pasos, el modelo de
   trazabilidad y el mecanismo de anulación.
6. Al armar el dict de `020`, contemplar el caso `FORMA-PAGO = "MP"` /
   `DISPON-P = "9"` cuando la orden tiene más de un instrumento de pago (ver
   punto abierto #2) — no alcanza con derivarlo del primer `025`.

## Apéndice A — Especificación completa BBVA (extraída de `BBVA DDRR Pago a Proveedores.docx.pdf`)

Volcado íntegro del diseño de registro, campo por campo, tal como está en el
PDF oficial del banco ("FNC-Pago a Proveedores 05-2019", 59 páginas). Se
agrega acá — aunque varios registros quedan fuera del alcance de esta etapa
(sección 1) — porque ya está leído y es más barato tenerlo documentado ahora
que releer el PDF cuando se aborde una etapa futura.

Convenciones de todas las tablas: `Tipo` `N`=numérico entero, `A`=alfanumérico;
`Oblig.` `SI`/`NO`; `Long.`/`Inicio` en caracteres, 1-indexado. Todos los
registros terminan con un `FILLER` de espacios hasta la posición 850 + `CR LF`.

### A.0 Reglas generales (aplican a todos los registros)

- **Codificación**: ANSI o ASCII. Sin separadores entre campos (posicional
  puro). 850 caracteres por línea + `CR LF`.
- **`IDENT-REGISTRO`** (pos 1-4, todos los registros): fijo `0306`.
- **`TIPO-REG`** (pos 5-7, todos los registros): el código de 3 dígitos del
  registro (`010`/`020`/.../`095`).
- **`TIPO-DOC-EMPRE`** (pos 8-11, casi todos los registros): fijo `CUIT`.
- **`NRO-CUIT-EMPRE`** (pos 12-24, long 13, casi todos los registros): CUIT
  de la empresa emisora del pago, ceros a la izquierda.
- **`SECUENCIA`** (pos 25-30, long 6, **todos los registros sin excepción**):
  número correlativo. Fórmula documentada explícitamente en el PDF: **"Número
  de fila – 1"**, con ceros a la izquierda. Es decir, es un contador global
  de líneas del archivo completo (la primera línea, el `010`, tiene secuencia
  `000000`), no un contador por tipo de registro ni por orden de pago. Esto
  coincide con lo observado en los archivos reales (ver sección 4 del cuerpo
  del documento).
- **Campo numérico** → ceros a la izquierda. **Campo alfanumérico** → espacios
  a la derecha. Los importes son siempre numéricos con 2 decimales implícitos
  (los últimos 2 dígitos del campo, sin separador).
- **Registros disponibles y cardinalidad** (pág. 9):

  | Registro | Descripción | Cardinalidad |
  |---|---|---|
  | 010 | cabecera de archivo | único |
  | 020 | cabecera de pago individual | 1 por cada pago |
  | 025 | multi-pago (instrumento adicional) | se puede repetir, 0+ por pago |
  | 030 | retención libre (2 sub-diseños: inicio/detalle y fin) | mín. 2 por retención libre |
  | 040 | detalle de pago "factura" | se puede repetir |
  | 060 | cabecera retención IIBB | se puede repetir (1 por jurisdicción) |
  | 070 | detalle retención IIBB | se puede repetir |
  | 080 | retenciones especiales | se puede repetir |
  | 090 | pie de pago individual (datos del proveedor) | relación 1 a 1 con el 020 |
  | 095 | pie de archivo | único |

- **Orden de bloques** (ejemplos pág. 8-9, ya confirmado contra los 3 archivos
  reales): `010`, luego por cada orden de pago: `020` + (`025`+)? + (`040`+)? +
  (`060`+`070`+)? + (`080`+)? + `090`, y al final `095`. Si la orden usa
  retenciones "libre impresión" (`LIBRE-IMPRESIÓN=S` en el 010), después del
  `020` solo se aceptan `025`, `030`, `040` y `090` — no `060`/`070`/`080`.

### A.1 Registro 010 — cabecera de archivo (único)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1 | IDENT-REGISTRO | N | SI | 4 | 1 | Fijo `0306` |
| 2 | TIPO-REG | N | SI | 3 | 5 | Fijo `010` |
| 3 | TIPO-DOC-EMPRE | A | SI | 4 | 8 | Fijo `CUIT` |
| 4 | NRO-CUIT-EMPRE | N | SI | 13 | 12 | CUIT de la empresa |
| 5 | SECUENCIA | N | SI | 6 | 25 | Fijo `000000` en cabecera |
| 6 | MONEDA | N | SI | 1 | 31 | Fijo `0` (pesos) |
| 7 | IMPORTE | N | SI | 13 | 32 | Suma del campo IMPORTE de todos los `020` del archivo, 2 decimales implícitos |
| 8 | FORMA-PAGO | A | SI | 2 | 45 | `AB`/`CH`/`EC`/`99` (distintas formas). **Recomendado usar `99`** e informar la forma real en cada `020` |
| 9 | FORMA-COBRO | N | SI | 1 | 47 | Fijo `0` |
| 10 | DISPON-PAGO | N | SI | 1 | 48 | Depende de FORMA-PAGO (ver tabla de códigos DISPON en A.9 más abajo). Si FORMA-PAGO=`99`: usar `9` (libre, se define en cada 020) |
| 11 | DEPÓSITO | N | SI | 1 | 49 | Fijo `0` |
| 12 | FECHA-EMISIÓN | N | SI | 8 | 50 | `AAAAMMDD`, fecha hábil ≥ hoy |
| 13 | FECHA-ENTREGA | N | SI | 8 | 58 | `AAAAMMDD`. Si se quieren fechas distintas por pago: completar con `99999999` acá e informar la real en cada `020` |
| 14 | FECHA-PAGO | N | SI | 8 | 66 | Ídem: `99999999` acá si varía por pago, dato real en el `020` |
| 15 | ENTIDAD | N | SI | 4 | 74 | Fijo `0017` (código de BBVA) |
| 16 | SUC-CTA-DÉBITO | N | SI | 4 | 78 | Sucursal de la cuenta débito (pedir al implementador) |
| 17 | DV-CTA-DÉBITO | N | SI | 2 | 82 | Dígito verificador (lo da el banco) |
| 18 | TIPO-CTA-DÉBITO | N | SI | 2 | 84 | **Fijo `01`** |
| 19 | MONEDA-CTA-DÉBITO | N | SI | 1 | 86 | **Fijo `0`** |
| 20 | NRO-CTA-DÉBITO | N | SI | 7 | 87 | Número de cuenta débito (pedir al implementador) |
| 21 | CANTIDAD-INST | N | SI | 7 | 94 | Cantidad de registros `020` del archivo |
| 22 | ENTREGA-LOTE | A | NO | 1 | 101 | `S` si todos los cheques se entregan en una única sucursal; si no, espacio |
| 23 | SUC-ENTREGA-LOTE | A | NO | 4 | 102 | Sucursal de entrega si `ENTREGA-LOTE=S`; si no, espacios |
| 24 | FILLER | A | SI | 6 | 106 | Espacios |
| 25 | LIBRE-IMPRESIÓN | A | NO | 1 | 112 | `S` = comprobantes de retención con formato propio del cliente (implica reglas de relleno fijo en 020/040, ver PDF pág. 16-17) |
| 26 | NOMBRE-FICHERO | A | NO | 12 | 113 | Puede ir en blanco |
| 27 | FECHA-PROCESO | N | SI | 8 | 125 | `AAAAMMDD`, fecha de generación/envío |
| 28 | CONTRATO PROV | A | SI | 20 | 133 | Número de contrato del emisor (pedir al implementador) |
| 29 | FILLER | A | SI | 698 | 153 | Espacios hasta 850 |

### A.2 Registro 020 — orden de pago (1 por cada pago)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-4 | IDENT-REGISTRO / TIPO-REG=`020` / TIPO-DOC-EMPRE / NRO-CUIT-EMPRE | | | | 1-24 | Ver A.0 |
| 5 | SECUENCIA | N | SI | 6 | 25 | Ver A.0 |
| 6 | PRO-NRO-BENEFICIARIO | N | SI | 15 | 31 | Identifica al proveedor; debe ser igual al mismo campo del `090` (ver punto abierto #1) |
| 7 | NRO-MINUTA | N | SI | 8 | 46 | Número de OP, correlativo, no reutilizable. Debe coincidir con `PRO-MINUTA` del `090` |
| 8 | IMPORTE | N | SI | 13 | 54 | Importe neto del pago, 2 decimales implícitos |
| 9 | NRO-CERT-RET-GANANCIAS | A | NO | 14 | 67 | Si hay retención de Ganancias |
| 10 | RÉGIMEN-GANANCIAS | A | NO | 30 | 81 | Ídem |
| 11 | IMP-RET-GANANCIAS | N | NO | 13 | 111 | Importe único por pago; requiere un `040` con código GA/IG |
| 12 | NRO-CERT-RET-IVA | A | NO | 14 | 124 | Si hay retención de IVA |
| 13 | RÉGIMEN-IVA | A | NO | 30 | 138 | Ídem |
| 14 | PRO-NRO-ORD | A | SI | 15 | 168 | Debe coincidir con el mismo campo del `090` |
| 15 | FILLER | A | SI | 8 | 183 | Espacios |
| 16 | ACRED-A-SUSP | A | NO | 1 | 191 | Espacio |
| 17 | IPERMFIN | A | NO | 1 | 192 | Solo si FORMA-PAGO=`CH`: `S`/`N`/espacio, financiación automática al proveedor |
| 18 | CLI-AJE | A | NO | 1 | 193 | Solo si FORMA-PAGO=`AB`: `S` si la cuenta destino es de otro banco, espacio si es BBVA (ver lógica en A.8) |
| 19 | NCUIT-PAGO | N | NO | 13 | 194 | Solo si el destinatario del cheque difiere del de la minuta |
| 20 | NOME-PAGO | A | NO | 40 | 207 | Ídem |
| 21 | TIPO-DOCUMENTO | A | SI | 3 | 247 | `CUI`=CUIT, `CUL`=CUIL — debe coincidir con el `090` |
| 22 | NRO-DOCUMENTO | A | SI | 11 | 250 | Ídem |
| 23 | SUC-ENTREGA | N | SI | 4 | 261 | Sucursal de entrega |
| 24 | FECHA-ENTREGA | N | NO | 8 | 265 | Solo si no se completó en el 010 |
| 25 | FECHA-PAGO | N | NO | 8 | 273 | Solo si no se completó en el 010. **Si se usa el registro 025, acá va `9`** (repetido) |
| 26 | FORMA-PAGO | A | NO | 2 | 281 | `AB`/`CH`/`EC`/**`MP`** (más de un instrumento por la misma orden — ver punto abierto #2). Si se informó en el 010, dejar en blanco acá |
| 27 | FORMA-COBRO | N | SI | 1 | 283 | Fijo `0` |
| 28 | DISPON-P | N | NO | 1 | 284 | Depende de FORMA-PAGO (tabla en A.9). **Si FORMA-PAGO=`MP`: acá va `9`**, y el código real de cada instrumento se informa en su respectivo `025` |
| 29 | DEPÓSITO | N | NO | 1 | 285 | Fijo `0` |
| 30 | NRO-CHEQUE | N | NO | 13 | 286 | Ceros, o si hay chequera virtual arranca con `8` |
| 31 | COD-DEVOLUCIÓN | A | NO | 6 | 299 | Solo en archivos de devolución del banco |
| 32 | DESC-DEVOLUCIÓN | A | NO | 40 | 305 | Ídem |
| 33 | FILLER | A | SI | 506 | 345 | Espacios hasta 850 |

**Hallazgo clave (validado contra archivos reales, ver punto abierto #2):**
cuando una orden se paga con más de un instrumento, el `020` de esa orden usa
`FORMA-PAGO="MP"` + `DISPON-P="9"` + `FECHA-PAGO="99999999"`, y cada
instrumento real (tipo, fecha de pago, importe, forma de pago concreta) se
informa en su propio registro `025`.

### A.3 Registro 025 — multi-pago / instrumento adicional

Se usa para emitir más de un instrumento de pago dentro de la misma orden
(ej. una OP que se cancela con 2 Echeqs: van 2 registros `025` después del
`020` y antes del `090`).

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | IDENT-REGISTRO / TIPO-REG=`025` / TIPO-DOC-EMPRE / NRO-CUIT-EMPRE / SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | FILLER | A | SI | 15 | 31 | Espacios |
| 7 | NRO-MINUTA | N | SI | 8 | 46 | Igual al `NRO-MINUTA` (ID 7) del `020` que lo contiene |
| 8 | IMPORTE | N | SI | 13 | 54 | Importe de **este** instrumento, 2 decimales implícitos |
| 9 | FILLER | A | SI | 125 | 67 | Espacios |
| 10 | IPERMFIN | A | NO | 1 | 192 | Solo si FORMA-PAGO=`CH` de este instrumento |
| 11 | FILLER | A | SI | 58 | 193 | Espacios |
| 12 | PRO-CBU-NRO | N | NO | 22 | 251 | Obligatorio si FORMA-PAGO=`AB`; si se informa acá no hace falta en el `090` |
| 13 | FECHA-PAGO | N | SI | 8 | 273 | `AAAAMMDD`, fecha de pago de **este** instrumento |
| 14 | FORMA-PAGO | A | SI | 2 | 281 | `AB`/`CH`/`EC` (el tipo real de este instrumento en particular) |
| 15 | FILLER | A | SI | 1 | 283 | Espacio |
| 16 | DISPON-P | N | SI | 1 | 284 | Código real de disponibilidad de este instrumento (tabla A.9) |
| 17 | FILLER | A | SI | 1 | 285 | Espacio |
| 18 | NRO-CHEQUE | N | NO | 13 | 286 | Ceros, o arranca con `8` si es chequera virtual |
| 19 | COD-DEVOLUCIÓN | A | NO | 6 | 299 | Solo en devoluciones |
| 20 | DESC-DEVOLUCIÓN | A | NO | 40 | 305 | Ídem |
| 21 | FILLER | A | SI | 506 | 345 | Espacios hasta 850 |

Validado campo por campo contra `IMPA_OP_ECHEQS...txt` (4 instrumentos) y
`LUFRAN_OP_ECHEQS...txt` (7 instrumentos): coincide exacto, incluyendo
`FORMA-PAGO="EC"`, `NRO-CHEQUE` arrancando con `8` (chequera virtual,
incrementando 1 por instrumento) y `FECHA-PAGO` con vencimientos mensuales
escalonados (cuotas).

### A.4 Registro 030 — retención de libre impresión (fuera de alcance de esta etapa)

Tiene **dos sub-diseños** distintos (detalle no capturado en ninguna versión
anterior del análisis): un registro de "inicio del comprobante" (que además
sirve de detalle) y un registro de "fin del comprobante" — se repite el par
por cada comprobante, y "fin" cierra la secuencia de esa retención.

**Inicio/detalle:**

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | MIN-COMPROB | A | SI | 1 | 31 | Fijo `R` (cualquier tipo de retención) |
| 7 | REG-LIBRE | A | SI | 69 | 32 | Texto libre del comprobante/retención |
| 8 | FILLER | A | SI | 734 | 101 | Espacios |
| 9 | IMPORTE | N | SI | 13 | 835 | Ceros |
| 10 | FILLER | A | SI | 3 | 848 | Espacios hasta 850 |

**Fin del comprobante:**

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | MIN-COMPROB | A | SI | 1 | 31 | Fijo `R` |
| 7 | FILLER | A | SI | 754 | 32 | Espacios |
| 8 | DESCRIPCIÓN | A | SI | 49 | 786 | Concepto, alineado a la izquierda, sale en la minuta |
| 9 | IMPORTE | N | SI | 13 | 835 | Importe total del comprobante/retención, sale en la minuta |
| 10 | CÓDIGO-DB-CR | A | SI | 2 | 848 | `DB` (a favor del proveedor) o `CR` (deduce el monto) |

Si el pago tiene más de una retención, se repite el par inicio+fin por cada
una. Requiere coordinación previa con el banco y, si se usa, hay que omitir
la integración de los otros registros de retención (040/060/070/080).

### A.5 Registro 040 — detalle de comprobante (factura/NC/ND) (fuera de alcance)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | FILLER | A | SI | 2 | 31 | Espacios |
| 7 | FECHA-COMP-MINUTA | N | NO | 8 | 33 | `AAAAMMDD`; si no se informa, sale `0001-01-01` en la minuta |
| 8 | DESC-COMP-MINUTA | A | NO | 25 | 41 | Para impresión de comprobantes |
| 9 | COMP-DB-CR | A | SI | 2 | 66 | `CR` facturas/ND, `DB` NC |
| 10 | TIPO-COMP-MINUTA | A | NO | 1 | 68 | Para impresión |
| 11 | NRO-COMP-MINUTA | A | NO | 12 | 69 | Número de factura/documento |
| 12 | IMPORTE-COMP-MINUTA | N | SI | 13 | 81 | Importe bruto del comprobante |
| 13 | COD-IMPUESTO | A | NO | 2 | 94 | `IV`=IVA, `GA`=Ganancias, `IG`=ambos; blanco si no hay retención |
| 14 | ALÍCUOTA-1-MINUTA | N | NO | 5 | 96 | Alícuota IVA facturado (3+2 dígitos) |
| 15 | IMPORTE-1-MINUTA | N | NO | 13 | 101 | Importe del IVA facturado |
| 16 | ALÍCUOTA-2-MINUTA | N | SI* | 5 | 114 | *Obligatorio si COD-IMPUESTO=`IV`/`IG`. Alícuota de retención IVA |
| 17 | IMPORTE-2-MINUTA | N | SI* | 13 | 119 | *Ídem. Importe de la retención |
| 18 | FILLER | A | SI | 719 | 132 | Espacios hasta 850 |

### A.6 Registro 060 — cabecera retención IIBB (fuera de alcance)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | NRO-CERT-RET-IB | A | SI | 14 | 31 | Número de certificado de retención IIBB |
| 7 | COD-PCIA | N | SI | 4 | 45 | Código de provincia (tabla A.10) |
| 8 | NRO-INGB-BEN | A | SI | 11 | 49 | Nro. de Ingresos Brutos del beneficiario |
| 9 | FILLER | A | SI | 791 | 60 | Espacios hasta 850 |

Si hay retención de IIBB en más de una jurisdicción: se repite un `060` por
cada jurisdicción, seguido de sus `070` correspondientes.

### A.7 Registro 070 — detalle retención IIBB (fuera de alcance)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 7 | FECHA-COMP-IB | N | NO | 8 | 31 | Libre |
| 8 | DESC-COMP-IB | A | NO | 25 | 39 | Libre |
| 9 | TIPO-COMP-IB | A | NO | 1 | 64 | Libre |
| 10 | NRO-COMP-IB | A | NO | 12 | 65 | Libre |
| 11 | IMPORTE-COMP-IB | N | SI | 13 | 77 | Importe del comprobante |
| 12 | BASE-IMPONIBLE | N | SI | 13 | 90 | Base para el cálculo |
| 13 | ALÍCUOTA-1-IB | N | SI | 5 | 103 | 3+2 dígitos |
| 14 | IMPORTE-1-IB | N | SI | 13 | 108 | Importe de la retención |
| 15 | ALÍCUOTA-2-IB | N | NO | 5 | 121 | Si hay 2ª retención IIBB |
| 16 | IMPORTE-2-IB | N | NO | 13 | 126 | Ídem |
| 17 | ALÍCUOTA-3-IB | N | NO | 5 | 139 | Solo Provincia de San Luis |
| 18 | IMPORTE-3-IB | N | NO | 13 | 144 | Ídem |
| 19 | COD-DB-CR | A | SI | 2 | 157 | `DB`/`CR` |
| 20 | FILLER | A | SI | 692 | 159 | Espacios hasta 850 |

(Nota: el PDF numera del ID 5 directo al 7 en este registro — no hay un ID 6
documentado, posible salto en la numeración original del banco.)

### A.8 Registro 080 — retenciones especiales (fuera de alcance)

Antes de usar, "solicitar al implementador asignado el listado de retenciones
especiales" y notificar cuáles se van a usar.

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | CODIGO-RETENCION | A | SI | 3 | 31 | Pedir listado al implementador |
| 7 | CÓDIGO-PROVINCIA | A | NO | 4 | 34 | Tabla A.10 |
| 8 | NUMERO-CERTIFICADO | A | SI | 20 | 38 | |
| 9 | FECHA-RETENCIÓN | N | NO | 8 | 58 | |
| 10 | DESCRIPCIÓN-MOTIVO | A | NO | 25 | 66 | Libre |
| 11 | TIPO-COMPROBANTE | A | NO | 1 | 91 | Libre |
| 12 | NRO-COMPROBANTE | A | NO | 15 | 92 | Libre |
| 13 | IMPORTE-COMPROBANTE | N | SI | 13 | 107 | |
| 14 | BASE-IMPONIBLE | N | SI | 13 | 120 | |
| 15 | ALÍCUOTA-1 | N | SI | 5 | 133 | |
| 16 | IMPORTE-1 | N | SI | 13 | 138 | |
| 17 | ALÍCUOTA-2 | N | NO | 5 | 151 | Si hay 2ª retención igual |
| 18 | IMPORTE-2 | N | NO | 13 | 156 | Ídem |
| 19 | ALÍCUOTA-3 | N | NO | 5 | 169 | Ídem, 3ª |
| 20 | IMPORTE-3 | N | NO | 13 | 174 | Ídem |
| 21 | CÓDIGO-DB-CR | A | SI | 2 | 187 | |
| 22 | NRO-MATRICULA-RPV | A | NO | 15 | 189 | Ceros si no aplica |
| 23 | FILLER | A | NO | 647 | 204 | Espacios hasta 850 |

### A.9 Registro 090 — datos del proveedor (1 a 1 con el `020`)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 (nota: el PDF salta directo del ID 5 al 11 acá) |
| 11 | PRO-NRO-ORD | A | SI | 15 | 31 | Igual al mismo campo del `020` |
| 12 | PRO-NRO-BENEF | N | SI | 15 | 46 | Igual a `PRO-NRO-BENEFICIARIO` del `020` |
| 13 | PRO-EST-BENEF | A | SI | 1 | 61 | Fijo `1` |
| 14 | PRO-DOCTO-TIP | A | SI | 3 | 62 | `CUI`/`CUL`/`DNI`/`LC`/`LE`/`PAS`/`CIE`/`DNE`/`CDI`/`DUM`/`DUF` |
| 15 | PRO-DOCTO-NRO | N | SI | 11 | 65 | |
| 16 | PRO-DENOMINA | A | SI | 40 | 76 | Razón social del proveedor |
| 17 | PRO-CATEGO | A | NO | 2 | 116 | Espacios |
| 18 | PRO-PERMIT-FINAN | A | NO | 1 | 118 | Solo FORMA-PAGO=`CH` |
| 19 | PRO-CUS-TIP | N | NO | 2 | 119 | Ceros (legacy, bonos) |
| 20 | PRO-CUS-SUC | N | NO | 3 | 121 | Ídem |
| 21 | PRO-CUS-NRO | N | NO | 10 | 124 | Ídem |
| 22 | PRO-CBU-NRO | N | NO | 22 | 134 | Obligatorio si FORMA-PAGO=`AB` |
| 23 | PRO-INGBRTS | A | NO | 11 | 156 | |
| 24 | PRO-CALLE | A | SI | 24 | 167 | |
| 25 | PRO-NUMERO | A | NO | 5 | 191 | |
| 26 | PRO-DEPTO | A | NO | 3 | 196 | |
| 27 | PRO-PISO | A | NO | 2 | 199 | |
| 28 | PRO-LOCALID | A | NO | 28 | 201 | |
| 29 | PRO-CPOSTAL | A | NO | 5 | 229 | |
| 30 | PRO-CODPROV | A | SI | 2 | 234 | Tabla A.10 |
| 31 | PRO-CODPAIS | A | SI | 3 | 236 | Fijo `080` (Argentina) |
| 32 | PRO-EMAIL | A | SI | 40 | 239 | |
| 33-40 | PRO-*-ENTREGA (calle/número/depto/piso/localidad/CP/provincia/país entrega) | A | NO | — | 279-350 | Domicilio de entrega alternativo — no obligatorio para Echeq |
| 41-45 | PRO-TELEF-* (tipo/prefijo/característica/número/interno) | A | NO | — | 351-383 | Tabla de tipos: 01 Teléfono, 02 Télex, 03 Celular, 04 Fax, 05 Radiollamada, 06 Radio, 07 Comunitario |
| 46-50 | PRO-TELEF-ALTER-* | A | NO | — | 384-416 | Ídem, teléfono alternativo |
| 51-53 | PRO-AUTORIZA-NOM1/TIP1/DOC1 | A/A/N | SI | 25/3/8 | 417/442/445 | Autorizado 1 a retirar el cheque — **obligatorio si FORMA-PAGO=CH** (máx. 3 autorizados) |
| 54-56 | PRO-AUTORIZA-NOM2/TIP2/DOC2 | A/A/N | NO | 25/3/8 | 453/478/481 | Autorizado 2 |
| 57-59 | PRO-AUTORIZA-NOM3/TIP3/DOC3 | A/A/N | NO | 25/3/8 | 489/514/517 | Autorizado 3 |
| 60 | PRO-DATOS | A | NO | 100 | 525 | Información adicional libre |
| 61 | PRO-MINUTA | N | SI | 8 | 625 | Debe coincidir con `NRO-MINUTA` del `020` |
| 62 | FILLER | A | SI | 217 | 633 | Espacios hasta 850 |

### A.10 Registro 095 — pie de archivo (único)

| ID | Campo | Tipo | Oblig. | Long. | Inicio | Observaciones |
|---|---|---|---|---|---|---|
| 1-5 | ...SECUENCIA | | | | 1-30 | Ver A.0 |
| 6 | SUMA-IMPORTE | N | SI | 13 | 31 | Suma de importes de todas las OP del lote |
| 7 | CANT-PAGOS | N | SI | 7 | 44 | Cantidad de registros `020` |
| 8 | TOT-REG | N | SI | 10 | 51 | Cantidad total de registros del archivo, incluyendo cabecera y pie |
| 9 | FILLER | A | NO | 790 | 61 | Espacios hasta 850 |

### A.11 Tabla de provincias (para `PRO-CODPROV` / `COD-PCIA` / `CÓDIGO-PROVINCIA`)

| Código | Provincia | Código | Provincia |
|---|---|---|---|
| 0001 | Capital Federal | 0013 | Mendoza |
| 0002 | Buenos Aires | 0014 | Misiones |
| 0003 | Catamarca | 0015 | Neuquén |
| 0004 | Córdoba | 0016 | Río Negro |
| 0005 | Corrientes | 0017 | Salta |
| 0006 | Chaco | 0018 | San Juan |
| 0007 | Chubut | 0019 | San Luis |
| 0008 | Entre Ríos | 0020 | Santa Cruz |
| 0009 | Formosa | 0021 | Santa Fe |
| 0010 | Jujuy | 0022 | Santiago del Estero |
| 0011 | La Pampa | 0023 | Tucumán |
| 0012 | La Rioja | 0040 | Tierra del Fuego |

Para Odoo, esto es un catálogo fijo a mapear contra `res.country.state` (o
directo por diccionario en el código, dado que son solo 24 valores y no
cambian). **Nota**: el código de provincia de BBVA (`PRO-CODPROV`, long 2 en
el 090, pero `COD-PCIA` long 4 en el 060) no tiene relación numérica con el
`state_id` interno de Odoo — hay que armar el diccionario de mapeo a mano.

### A.12 Validación de importes (pág. 6-7)

```
Importe del Pago = Importe Comprobante - Retenciones
```

- **Importe del Pago**: `IMPORTE` del registro 020 (neto).
- **Importe Comprobante**: `IMPORTE-COMP-MINUTA` del 040, con signo
  (`COMP-DB-CR`: `CR`=facturas/ND, `DB`=NC) y código de impuesto
  (`COD-IMPUESTO`: vacío=sin retención, `GA`=solo Ganancias, `IV`=solo IVA,
  `IG`=IVA+Ganancias).
- **Retenciones** (cada una con su propio importe y signo `DB`/`CR`):
  IVA (`IMPORTE-2-MINUTA`, a nivel comprobante), Ganancias
  (`IMP-RET-GANANCIAS`, único por pago, en el 020), Ingresos Brutos
  (`IMPORTE-1-IB`, a nivel comprobante y jurisdicción), Otras Retenciones
  (`IMPORTE-1` del 080, a nivel comprobante y tipo de retención).

### A.13 Validación de fechas (pág. 6-7)

Depende de `FORMA-PAGO`:

- **`AB`** (transferencia): fecha de entrega no se controla. Fecha de Pago ≥
  Fecha de Emisión; Emisión ≥ hoy; Emisión y Pago deben ser días hábiles.
- **`CH`** (cheque): Fecha de Entrega ≥ Fecha de Emisión; Fecha de Pago >
  Fecha de Entrega; Emisión ≥ hoy; Emisión y Entrega hábiles. Para "cheque al
  día" las 3 fechas deben ser iguales y hábiles.
- Si se usa el registro `025` (multi-instrumento), la fecha de pago del
  `020` va con `9` repetido y cada `025` lleva su propia `FECHA-PAGO`.

### A.14 Validaciones de datos del proveedor (pág. 10-11)

- **Transferencias a CBU**: el BCRA valida la terna (tipo de documento,
  número de documento, número de CBU) contra una tabla única entre bancos —
  si no coincide, la operación se rechaza. *Implicancia para Odoo*: conviene
  validar/depurar esa terna en el partner antes de exportar, no solo confiar
  en que el CBU esté cargado.
- **`CLI-AJE`** (020, pos 193): marca si el CBU destino es de otro banco.
  Lógica documentada explícitamente: si los primeros 3 dígitos del CBU son
  `017` (BBVA/Francés) → `CLI-AJE=" "` (espacio); si no → `CLI-AJE="S"`.
- **Emisión de cheques**: se valida contra tabla (tipo de documento, número
  de documento, número de cheque "según la contratación").
- **Autorizados a retirar cheque físico**: obligatorio informar al menos 1
  (hasta 3) si `FORMA-PAGO=CH` — si la persona que va a la sucursal no
  coincide con la informada, el banco niega la entrega.

### A.15 Tabla de códigos DISPON (referida desde 010/020/025)

Según `FORMA-PAGO`:

| Código | Si FORMA-PAGO=CH o EC | Si FORMA-PAGO=AB |
|---|---|---|
| 0 | CPD cruzado no a la orden | Contrato (según lo acordado con el gestor comercial) |
| 1 | CPD cruzado a la orden | COELSA |
| 2 | CPD no cruzado a la orden | CCI (Cámara Interbanking) |
| 3 | CPD no cruzado no a la orden | — |
| 4 | Cheque al día cruzado no a la orden | — |
| 5 | Cheque al día cruzado a la orden | — |
| 6 | Cheque al día no cruzado a la orden | — |
| 7 | Cheque al día no cruzado no a la orden | — |
| 9 | Libre (si FORMA-PAGO=`99`/`MP` en el 010/020) | — |

**Nota**: para `FORMA-PAGO=EC` el PDF documenta valores 0-7 en el registro
010/020, pero en el registro **025** solo permite `1, 2, 5, 6` (los "a la
orden") — es decir, para Echeq multi-instrumento el banco restringe a
CPD/cheque al día "a la orden" únicamente.

### A.16 Circuito operativo (fuera del alcance del exportador, pero útil para el flujo de UX)

1. El archivo se sube por BBVA Net Cash vía *Operaciones → Envío de
   Archivos*, modo "Incorporación", tipo "PAP-Pago a Proveedores", banco
   BBVA.
2. Tras subirlo, queda en validación de estructura. Se consulta en
   *Operaciones → Situación de Archivos Creados*, filtrando "No Enviados".
   Puede quedar **Rechazado** (error de estructura, ver detalle por línea) o
   **Pendiente de Firmas** (estructura OK).
3. Firma: menú *Firmas → Pendientes de Firma*, seleccionar, firmar con Clave
   de Operaciones (9 dígitos) + Clave Token, y enviar.
4. **Verificación de estado de pagos** — dos vías, mutuamente excluyentes (se
   configura una u otra con el banco):
   - **Devolución tradicional**: el banco reenvía un archivo con el mismo
     formato del enviado, tantas veces como haga falta hasta el estado
     final.
   - **Devolución consolidada**: un archivo por día con el estado de los
     pagos del día + actualizaciones de días anteriores, en un formato
     distinto (no es el archivo original).
   - Se descargan desde *Servicios Adicionales → Descargas → Descarga de
     archivos*, buzón "Pendiente", tipo "DVP" (tradicional) o "DCP"
     (consolidada). Quedan en el histórico ~60 días.
   - *Implicancia para Odoo*: si en el futuro se quiere automatizar la
     conciliación de vuelta (marcar OPs como pagadas/rechazadas según la
     devolución del banco), haría falta un segundo exportador/importador —
     no está pedido en el alcance actual, pero es la contraparte natural de
     este módulo.

## Apéndice B — Cruce de campos BBVA ↔ modelos Odoo

Todos los nombres de campo de esta sección están verificados leyendo el
código real del repo (no son supuestos de la matriz del cliente). Se cita
`archivo:línea` donde corresponde. Alcance: registros **010, 020, 025, 090,
095** (los de esta etapa). Los ejemplos usan los datos reales de
`JUMI_OP_ECHEQS_2026-06-23.txt` (CUIT empresa `30-53788287-1`, proveedor
"Goldstein, Mario" CUIT `20-13980273-0`) para poder validarlos contra el
archivo de ejemplo ya decodificado en el Apéndice A.

### B.0 Hallazgos clave del cruce (lo no evidente)

1. **`FORMA-PAGO` (AB/CH/EC) no es un campo directo en Odoo.** No existe un
   selection "forma de pago" en `account.payment.order`. Se **deriva** de
   dónde está imputado el pago:
   - Transferencia (`AB`) → la OP tiene líneas en
     `payment_mode_line_ids` (modelo `account.payment.mode.line`,
     `account_payment_order.py:2194-2254` — `payment_mode_id` es en
     realidad un `account.journal`, no un catálogo de formas de pago).
   - Cheque/Echeq (`CH`/`EC`) → la OP tiene registros en
     `issued_check_ids` (`account.check`, domain `internal_type=issued`).
     Para distinguir `CH` de `EC` se usa `account.check.checkbook_format`
     (`account_check.py:95-102`, selection **`physical`/`echeq`** — 2
     valores, sin ambigüedad: `physical`→`CH`, `echeq`→`EC`).
   - Si la OP combina ambos instrumentos → `FORMA-PAGO="MP"` (ver punto
     abierto #2 / A.2), con el detalle de cada uno en su propio `025`.

2. **El CBU de `res.company.cbu` NO es necesariamente la cuenta de débito de
   Pago a Proveedores.** Ese campo (`res_company.py:20-26`) está pensado para
   "CBU para Facturas A" — un uso distinto. La cuenta de débito real para
   BBVA sale del **`account.journal`** que se selecciona en el wizard (así
   lo dice ya la sección 3 del cuerpo del análisis), y su CBU/cuenta bancaria
   sale de `journal_id.bank_account_id` (`res.partner.bank`). **No mezclar
   ambos CBU.**

3. **`checkbook_format` (en `account.check`) vs `format` (en
   `account.payment.method.line`) son dos campos DISTINTOS, no confundir:**
   - `account.check.checkbook_format`: `physical`/`echeq` (2 valores) — sirve
     para `FORMA-PAGO`/`DISPON-P` (ver punto 1).
   - `account.payment.method.line.format` (el talonario, no el cheque
     individual): `physical`/`virtual`/`echeq` (3 valores) — **este es el
     que indica "chequera virtual"**, necesario para decidir si
     `NRO-CHEQUE` arranca con `"8"` (regla BBVA, A.2/A.3 ID 30/18):
     `check.checkbook_id.format == 'virtual'`.

4. **No hay campo de "sucursal de cuenta" ni "dígito verificador de cuenta"
   en ningún lado del repo** (confirmado por grep en todo el árbol). Esto
   reconfirma lo ya anotado en la sección 4.1: `SUC_CTA_DEBITO` y
   `DV_CTA_DEBITO` son 100% nuevos — no hay ningún campo Odoo existente del
   que puedan derivarse, van a vivir en configuración nueva (ver B.5).

5. **`res.country.state` no tiene ningún código que coincida con la tabla de
   provincias de BBVA** (Apéndice A.11) — el único campo propio agregado acá
   es `cot_code` (2 caracteres, para otro propósito). Hace falta un
   diccionario manual `state.id → código BBVA` (24 entradas, ver B.6).

6. **`res.partner.l10n_latam_identification_type_id` no mapea 1 a 1** con
   los códigos de tipo de documento de BBVA. Los tipos activos en este Odoo
   son `CUIT`, `DNI`, `CUIL`, `CDI`, `LE`, `LC`, `Sigd` (nombre del registro,
   no código) — BBVA espera `CUI`/`CUL`/`DNI`/`LC`/`LE`/`PAS`/`CIE`/`DNE`/
   `CDI`/`DUM`/`DUF`. Hace falta un diccionario de traducción (ver B.6).

### B.1 Registro 010 — cabecera

| Campo BBVA | Origen Odoo | Ejemplo |
|---|---|---|
| `NRO-CUIT-EMPRE` | `company_id.vat` (estándar, vía `res.partner`) | `30537882871` |
| `MONEDA` | fijo `0` | `0` |
| `IMPORTE` | `sum(payment_orders.mapped('amount'))` de las OPs seleccionadas en el wizard | suma en centavos, `moneyfmt` |
| `FORMA-PAGO` | fijo `99` (recomendado por el propio PDF — se informa por OP en el `020`) | `99` |
| `DISPON-PAGO` | fijo `9` (coherente con `FORMA-PAGO=99`) | `9` |
| `FECHA-EMISIÓN` | `fields.Date.context_today()` al momento de generar | `20260729` |
| `FECHA-ENTREGA` / `FECHA-PAGO` | fijo `99999999` (se informa por OP/instrumento) | `99999999` |
| `ENTIDAD` | fijo `0017` | `0017` |
| `SUC-CTA-DÉBITO` / `DV-CTA-DÉBITO` / `NRO-CTA-DÉBITO` | **nuevos**, no existen en Odoo (ver B.0.4) — config nueva ligada al `account.journal` elegido | a definir |
| `TIPO-CTA-DÉBITO` | fijo `01` | `01` |
| `MONEDA-CTA-DÉBITO` | fijo `0` | `0` |
| `CANTIDAD-INST` | `len(payment_orders)` | `2` |
| `NOMBRE-FICHERO` | opcional, en blanco | — |
| `FECHA-PROCESO` | igual a `FECHA-EMISIÓN` | `20260729` |
| `CONTRATO PROV` | **nuevo**, config nueva (pedir al implementador BBVA) | a definir |

### B.2 Registro 020 — orden de pago (loop sobre `account.payment.order`)

| Campo BBVA | Origen Odoo | Ejemplo |
|---|---|---|
| `NRO-CUIT-EMPRE` | `payment_order.company_id.vat` | `30537882871` |
| `PRO-NRO-BENEFICIARIO` | a definir (punto abierto #1) — candidato: `payment_order.partner_id.id` con algún padding/mapeo, o secuencia propia | `000000000000005` |
| `NRO-MINUTA` | `payment_order.number` (limpiando `/` si tiene) | `00078811` |
| `IMPORTE` | `payment_order.amount`, formateado con `moneyfmt(amount, places=2, ndigits=13, dp='')` | `0000006898325` (=$68.983,25) |
| `PRO-NRO-ORD` | mismo valor que en el `090` — candidato: nombre de archivo o `payment_order.number` | — |
| `IPERMFIN` | fijo `N` (Echeq no permite financiación automática por defecto, según ejemplo real) | `N` |
| `CLI-AJE` | solo si `FORMA-PAGO=AB`: `"S"` si `partner_id.bank_ids` (CBU, `acc_type='cbu'`) no empieza con `017`, sino espacio (lógica exacta en A.14) | — |
| `TIPO-DOCUMENTO` / `NRO-DOCUMENTO` | `partner_id.l10n_latam_identification_type_id` (traducido con dict B.6) / `partner_id.vat` | `CUI` / `20139802730` |
| `FECHA-ENTREGA` / `FECHA-PAGO` | `payment_order.date_effective` / `payment_order.date_due` (a confirmar cuál corresponde a cada uno) | `AAAAMMDD` |
| `FORMA-PAGO` | derivado (B.0.1): `AB` si hay `payment_mode_line_ids`, `CH`/`EC` según `issued_check_ids.checkbook_format` si hay un solo cheque, **`MP`** si `len(issued_check_ids) > 1` | `EC` o `MP` |
| `DISPON-P` | tabla A.15, según `FORMA-PAGO`. Si `MP`: fijo `9` | `1` (CPD cruzado a la orden) o `9` |
| `NRO-CHEQUE` | `issued_check_ids.number`, ceros a la izq., o si `checkbook_id.format=='virtual'` arranca con `8` (B.0.3) | `80001015` + relleno |

### B.3 Registro 025 — instrumento adicional (loop sobre `issued_check_ids[1:]` cuando hay más de uno)

| Campo BBVA | Origen Odoo | Ejemplo |
|---|---|---|
| `NRO-MINUTA` | igual al `020` que lo contiene (`payment_order.number`) | `00000698` |
| `IMPORTE` | `check.amount` (el importe de **este** cheque/Echeq, no el total de la OP) | `moneyfmt(check.amount, ...)` |
| `IPERMFIN` | igual que en el `020`, fijo `N` para Echeq | `N` |
| `FECHA-PAGO` | `check.payment_date` (acá sí varía por instrumento — son las cuotas escalonadas, ver A.3) | `20260619`, `20260720`... |
| `FORMA-PAGO` | `check.checkbook_format` traducido (`physical`→`CH`, `echeq`→`EC`) | `EC` |
| `DISPON-P` | tabla A.15/A.9, valor real de este instrumento (no `9`) | `1` |
| `NRO-CHEQUE` | `check.number`, con la regla del `8` si `checkbook_id.format=='virtual'` | `80001016` |

### B.4 Registro 090 — datos del proveedor (`payment_order.partner_id`)

| Campo BBVA | Origen Odoo | Ejemplo |
|---|---|---|
| `PRO-NRO-ORD` | igual al `020` (ver B.2) | — |
| `PRO-NRO-BENEF` | igual a `PRO-NRO-BENEFICIARIO` del `020` (B.2) | `000000000000005` |
| `PRO-EST-BENEF` | fijo `1` | `1` |
| `PRO-DOCTO-TIP` | `partner_id.l10n_latam_identification_type_id.name`, traducido con dict B.6 | `CUI` |
| `PRO-DOCTO-NRO` | `partner_id.vat` | `20139802730` |
| `PRO-DENOMINA` | `partner_id.name` | `Goldstein, Mario` |
| `PRO-PERMIT-FINAN` | igual criterio que `IPERMFIN` del 020 | `N` |
| `PRO-CBU-NRO` | `partner_id.bank_ids.filtered(lambda b: b.acc_type == 'cbu').acc_number` (solo si `FORMA-PAGO=AB`) | ceros si no aplica (Echeq) |
| `PRO-INGBRTS` | `partner_id.l10n_ar_gross_income_number` o similar (a confirmar nombre exacto — pendiente de research adicional si se activa IIBB en etapa futura) | — |
| `PRO-CALLE` / `PRO-NUMERO` / `PRO-LOCALID` / `PRO-CPOSTAL` | `partner_id.street` (a separar calle/altura si Odoo los tiene juntos) / `partner_id.city` / `partner_id.zip` | `General Guido 1455` |
| `PRO-CODPROV` | `partner_id.state_id`, traducido con dict B.6 (no hay campo directo, B.0.5) | `02` (Buenos Aires) |
| `PRO-CODPAIS` | fijo `080` (si `partner_id.country_id` es Argentina — para esta etapa asumimos siempre Argentina) | `080` |
| `PRO-EMAIL` | `partner_id.email` | `imprentageneralpaz@hotmail.com` |
| `PRO-AUTORIZA-*` | **no obligatorio para Echeq** — solo si `FORMA-PAGO=CH`; no hay campo Odoo hoy para "personas autorizadas a retirar cheque", quedaría fuera de alcance salvo que el cliente empiece a emitir CPD físico | ceros/espacios |
| `PRO-MINUTA` | igual a `NRO-MINUTA` del `020` | `00078811` |

### B.5 Registro 095 — totales (calculado sobre el recordset completo, no sale de un modelo)

| Campo BBVA | Origen |
|---|---|
| `SUMA-IMPORTE` | `sum(payment_orders.mapped('amount'))` — mismo valor que `IMPORTE` del 010 |
| `CANT-PAGOS` | `len(payment_orders)` |
| `TOT-REG` | `1 (010) + suma de líneas emitidas por OP (020 + 025 + 090 según corresponda) + 1 (095)` — se calcula contando cuántas líneas arma el wizard, no hay atajo de fórmula fija por la variabilidad del 025 |

### B.6 Diccionarios de mapeo necesarios (no existen como dato en Odoo, hay que armarlos a mano)

**Tipo de documento** (`l10n_latam.identification.type.name` → código BBVA,
usado en `TIPO-DOCUMENTO`/`PRO-DOCTO-TIP`):

| Odoo (`name`) | BBVA |
|---|---|
| CUIT | `CUI` |
| CUIL | `CUL` |
| DNI | `DNI` |
| LE | `LE` |
| LC | `LC` |
| CDI | `CDI` |
| Pasaporte (si existe / se activa) | `PAS` |

**Provincia** (`res.country.state.id` → código BBVA, tabla completa en
A.11): no hay atajo — 24 entradas fijas a mano, ej.
`{state_buenos_aires.id: '0002', state_cordoba.id: '0004', ...}`. Conviene
resolverlo por el `code` ISO de `res.country.state` si coincide con algún
patrón reconocible, o directo por `name` con un diccionario estático versionado
en Python (mismo criterio que usa `sicore_fixed_width_dicts.py` para otros
catálogos fijos de este repo).

### B.7 Patrón de armado de línea — `FixedWidth` (`l10n_ar_eynes/utils/sicore_fixed_width.py`)

Confirmado en la práctica (viendo `arba_fixed_width_dicts.py`): **todos los
campos se declaran `type: 'string'`**, incluidos los numéricos — el
formateo numérico se hace *antes*, con `moneyfmt()`, y el dict solo define
alineación y relleno:

```python
# Campo numérico (ej. IMPORTE del registro 020, pos 54, long 13)
'importe': {
    'start_pos': 54,
    'length': 13,
    'type': 'string',
    'alignment': 'right',
    'padding': '0',
    'required': True,
},
# Campo de texto (ej. PRO-DENOMINA del registro 090, pos 76, long 40)
'pro_denomina': {
    'start_pos': 76,
    'length': 40,
    'type': 'string',
    'alignment': 'left',
    'padding': ' ',
    'required': True,
},
```

Uso:

```python
fixed_width = FixedWidth(config_dict_020)
fixed_width.update(
    importe=moneyfmt(Decimal(str(payment_order.amount)), places=2, ndigits=13, dp=''),
    pro_denomina=payment_order.partner_id.name,
    ...
)
linea_020 = fixed_width.line  # string de 850 caracteres ya armado
```

`moneyfmt(Decimal('68983.25'), places=2, ndigits=13, dp='')` →
`'0000006898325'` — exactamente el formato que exige BBVA para `IMPORTE`.

El constructor de `FixedWidth` valida en `__init__` que no haya huecos ni
solapamientos entre campos (chequea que cada `start_pos` coincida con el
final acumulado del campo anterior) — es la misma garantía que ya se usó
para validar manualmente los 850 caracteres del Apéndice A.

### B.8 Patrón del wizard — aplicado a BBVA (basado en `arba_retention_exporter.py`)

Orden real de operaciones observado en el wizard de ARBA (a replicar tal
cual para BBVA):

1. Por cada línea del archivo: `fixed_width.update(**vals)` →
   `lineas.append(fixed_width.line)`.
2. Unir todas las líneas con `'\r\n'.join(...)` (+ el CRLF final).
3. Codificar a base64 (`_build_attachment_payload` o equivalente).
4. **Crear primero el registro de trazabilidad** (sin adjunto todavía).
5. **Recién después** crear el `ir.attachment`, con `res_model` apuntando al
   modelo de trazabilidad y `res_id` el id del registro creado en el paso 4.
6. `generated_file_rec.write({'attachment_id': attach_id.id})` para
   enlazarlo de vuelta.

Este orden importa: si se crea el adjunto antes que el registro de
trazabilidad, no hay `res_id` válido todavía.

### B.9 Modelo de trazabilidad — diseño concreto para BBVA

Clonando `arba.generated.files` (`models/arba_exporter.py:11-20`, campos
reales: `code`, `company_id`, `datas`/`datas_fname` relacionados al
`attachment_id`, `date_from`, `date_to`, `attachment_id`):

```python
class BbvaGeneratedFiles(models.Model):
    _name = 'bbva.generated.files'
    _description = 'Lote exportado a BBVA - Pago a Proveedores'

    code = fields.Char()
    company_id = fields.Many2one('res.company')
    date = fields.Datetime()
    amount_total = fields.Float()
    payment_order_ids = fields.Many2many('account.payment.order')
    attachment_id = fields.Many2one('ir.attachment')
    datas = fields.Binary(related='attachment_id.datas')
    datas_fname = fields.Char(related='attachment_id.name')
    # NO existe en arba.generated.files - hace falta agregarlo para BBVA
    # (sección 6.5 del análisis: anulación manual)
    state = fields.Selection([
        ('generated', 'Generado'),
        ('cancelled', 'Anulado'),
    ], default='generated')
    cancel_reason = fields.Text()
    cancel_uid = fields.Many2one('res.users')
    cancel_date = fields.Datetime()
```

Nota: la M2M `payment_order_ids` es la que permite el smart button
"Exportado a BBVA" en `account.payment.order` (sección 6.4 del cuerpo del
análisis) y también sirve para el guard anti-duplicado (chequear que
ninguna OP seleccionada ya esté en un lote `state=generated`).
