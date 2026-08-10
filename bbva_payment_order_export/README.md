# BBVA Payment Order Export

Módulo de Odoo 19 que agrega un wizard para generar el archivo TXT posicional
del servicio **"Pago a Proveedores"** de BBVA/Banco Francés, a partir de las
órdenes de pago (`account.payment.order`, modelo propio de `l10n_ar_eynes`)
canceladas con cheques o Echeqs.

## 1. Alcance implementado

El archivo es un TXT posicional de **850 caracteres por línea** (sin
separadores entre campos), codificación ANSI/ASCII, saltos de línea `CR LF`.
Registros implementados:

| Registro | Descripción | Cardinalidad |
|---|---|---|
| `010` | Cabecera del archivo | 1 por archivo |
| `020` | Orden de pago | 1 por cada orden de pago seleccionada |
| `025` | Instrumento adicional (multi-cheque/Echeq) | 1 por cada cheque/Echeq cuando la orden tiene **más de uno** |
| `090` | Datos del proveedor beneficiario | 1 por cada orden de pago (va después de su `020`/`025`) |
| `095` | Pie del archivo (totales) | 1 por archivo |

Orden de las líneas dentro del archivo:

```
010
  020  (orden de pago #1)
    025  (si tiene 2+ instrumentos: uno por cada cheque/Echeq)
    025
  090    (beneficiario de la orden #1)
  020  (orden de pago #2)
  090    (beneficiario de la orden #2, sin 025 si tiene un solo instrumento)
  ...
095
```

**Fuera de alcance de esta etapa** (documentados en el PDF oficial del banco,
pero no implementados): registros `030` (retención libre), `040` (detalle de
factura), `060`/`070` (retención IIBB) y `080` (retenciones especiales). Ver
`docs/ANALISIS_Y_DISENO.md` Apéndice A si se necesita abordarlos a futuro.

## 2. Arquitectura

- **Wizard** (`bbva.payment.order.export.wizard`, `TransientModel` — no
  persiste nada): único modelo del módulo. Se abre desde el menú
  *Contabilidad → Cuentas a pagar → Exportar a BBVA* o desde la acción
  contextual sobre la lista de órdenes de pago
  (`wizard/bbva_payment_order_export_wizard_views.xml`).
- **Motor de armado de línea**: se reutiliza `FixedWidth` + `moneyfmt()` de
  `l10n_ar_eynes/utils/sicore_fixed_width.py` (el mismo motor que usan los
  exportadores de SICORE/SIFERE/ARBA/ARCIBA). Cada línea se define como un
  diccionario de campos con `start_pos`, `length`, `alignment` (`left`/
  `right`) y `padding` (`' '` o `'0'`); `FixedWidth` valida que no haya
  huecos ni solapamientos entre campos y arma la línea completa.
- **Layout de cada registro**: dicts `REGISTRO_010`, `REGISTRO_020`,
  `REGISTRO_025`, `REGISTRO_090`, `REGISTRO_095` en
  `wizard/bbva_fixed_width_dicts.py`. Las posiciones/longitudes están
  validadas carácter por carácter contra archivos reales del banco (ver
  sección 6).
- **Sin modelo de trazabilidad todavía**: no existe un registro que
  persista "qué se exportó y cuándo" (a diferencia del patrón
  `arba.generated.files` de otros exportadores de este repo). El TXT se
  genera en memoria y solo se sube como `ir.attachment` colgado del propio
  wizard transitorio — no hay guard anti-doble-exportación ni smart button en
  la orden de pago. Ver "Pendiente" (sección 7).

## 3. Flujo de uso

1. **Selección**: el usuario elige compañía, una o varias órdenes de pago
   (`type='payment'`, `state='posted'`, de la compañía elegida), fecha de
   proceso, y los datos de la cuenta de débito BBVA (sucursal, dígito
   verificador, número de cuenta, contrato "Pago a Proveedores"). Estos
   últimos se piden en el wizard en cada exportación; todavía no hay una
   configuración persistente ligada al `account.journal` (ver sección 7).
2. **Validación** (botón *Previsualizar* o *Descargar TXT*, `_check_payment_orders`):
   - Todas las órdenes deben ser de la compañía elegida, tipo `payment` y
     estado `posted`.
   - Cada orden debe tener al menos un cheque/Echeq asociado
     (`issued_check_ids`).
   - Si tiene más de uno: la suma de los importes de los cheques/Echeqs debe
     coincidir con el importe de la orden (tolerancia 0,01), y los Echeqs
     usados en un `025` deben ser **"a la orden"** (restricción real del
     banco: en el registro `025`, un Echeq (`EC`) solo admite código
     `DISPON_P` 1, 2, 5 o 6 — ver tabla A.15 del análisis).
   - El proveedor de la orden debe ser argentino y tener completos: CUIT/CUIL,
     tipo de documento soportado, calle, localidad, código postal, provincia
     (mapeable a la tabla BBVA) y email.
   - Si algo falla, se listan todos los errores encontrados (por orden) antes
     de dejar avanzar.
3. **Previsualización** (`action_preview`): arma el archivo completo en
   memoria y lo muestra como texto monoespaciado en el propio formulario del
   wizard, sin generar ningún adjunto todavía.
4. **Descarga** (`action_download`): arma el archivo, lo codifica en
   `latin-1`, lo cuelga como `ir.attachment` del wizard, y dispara la
   descarga en el navegador. El nombre del archivo es
   `<Compañía>_OP_ECHEQS_<fecha>.txt`.

## 4. Detalle de campos por registro (origen de los datos en Odoo)

### 010 — Cabecera (una vez por archivo)

Agrega datos de la compañía (CUIT), del wizard (fecha de proceso, cuenta de
débito, contrato) y calculados sobre el lote completo (importe total = suma
de `amount` de las órdenes, cantidad de órdenes). `FORMA_PAGO` va fijo en
`99` y `DISPON_PAGO` en `9` (recomendado por el banco: la forma de pago real
se informa en cada `020`). `FECHA_ENTREGA`/`FECHA_PAGO` van fijos en
`99999999` (varían por orden). `TIPO_CTA_DEBITO` (`01`) y
`MONEDA_CTA_DEBITO` (`0`) son fijos según la especificación del banco.

### 020 — Orden de pago (una línea por cada `account.payment.order` seleccionada)

| Campo BBVA | Origen |
|---|---|
| `PRO_NRO_BENEFICIARIO` | `partner_id.id`, rellenado a 15 posiciones (identificador estable del proveedor — punto abierto de diseño, ver sección 7) |
| `NRO_MINUTA` | `payment_order.number` (solo dígitos) |
| `IMPORTE` | `payment_order.amount` |
| `PRO_NRO_ORD` | constante por archivo: `fecha_proceso + id del wizard` (no identifica la orden individual, identifica el lote — así lo espera el banco) |
| `TIPO_DOCUMENTO` / `NRO_DOCUMENTO` | tipo de documento del proveedor (traducido con diccionario `IDENTIFICATION_TYPE_BBVA`) / `partner_id.vat` |
| `FECHA_ENTREGA` | `payment_order.date_effective` |
| **Si la orden tiene un solo cheque/Echeq**: `FECHA_PAGO`, `FORMA_PAGO`, `DISPON_P`, `NRO_CHEQUE` | del único `account.check` asociado (ver reglas de abajo) |
| **Si la orden tiene 2+ cheques/Echeqs**: `FORMA_PAGO="MP"`, `DISPON_P="9"`, `FECHA_PAGO="99999999"`, `NRO_CHEQUE=0` | el detalle real de cada instrumento se informa en su propio `025` (regla del banco, validada contra archivos reales) |

### 025 — Instrumento adicional (una línea por cada `account.check` de la orden, solo si hay más de uno)

| Campo BBVA | Origen |
|---|---|
| `NRO_MINUTA` | igual al `020` que lo contiene |
| `IMPORTE` | `check.amount` (importe de **este** instrumento, no el total de la orden) |
| `IPERMFIN` | fijo `N` |
| `FECHA_PAGO` | `check.payment_date` (varía por instrumento — cuotas escalonadas) |
| `FORMA_PAGO` | `CH` (cheque físico) o `EC` (Echeq), según `check.checkbook_format` |
| `DISPON_P` | código real de modalidad de este instrumento (ver tabla más abajo) |
| `NRO_CHEQUE` | `check.number`, con el `8` inicial si es chequera virtual |
| `PRO_CBU_NRO` | se deja en ceros (solo aplica si `FORMA_PAGO=AB`, transferencia — no soportado todavía) |

### 090 — Datos del proveedor (una línea por orden, 1 a 1 con su `020`/`025`)

Sale de `payment_order.partner_id`: denominación, tipo/número de documento,
calle, localidad, código postal, provincia (traducida con
`PROVINCE_CODE_BBVA`), país (fijo `080`=Argentina), email. `PRO_NRO_ORD` y
`PRO_NRO_BENEF` repiten los mismos valores que el `020` de la orden.
`PRO_MINUTA` repite el número de orden.

### 095 — Pie del archivo (una vez, al final)

`SUMA_IMPORTE` y `CANT_PAGOS` son la suma de importes y la cantidad de
órdenes seleccionadas (mismos valores que el `010`). `TOT_REG` es la
cantidad total de líneas generadas (cabecera + 020/025/090 de cada orden +
pie) — no hay fórmula fija por línea porque varía según cuántos `025` tenga
cada orden.

## 5. Reglas y diccionarios especiales

- **`SECUENCIA`** (todos los registros, posición 25, largo 6): número de
  línea del archivo completo menos 1 (la cabecera `010` es la línea 1 →
  secuencia `000000`). Es un contador **global**, no por tipo de registro ni
  por orden.
- **Chequera virtual**: si `check.checkbook_id.format == 'virtual'`, el
  número de cheque/Echeq se completa con un `8` inicial (regla BBVA,
  `_nro_cheque_bbva`).
- **Tabla de modalidad (`DISPON_P`)**, según si el cheque es CPD (pago
  diferido, códigos 0-3) o al día (4-7), combinado con cruzado/no cruzado y
  a la orden/no a la orden (`_dispon_pago_bbva`):

  | Código | Cruzado | A la orden |
  |---|---|---|
  | 0 (CPD) / 4 (al día) | sí | no |
  | 1 (CPD) / 5 (al día) | sí | sí |
  | 2 (CPD) / 6 (al día) | no | sí |
  | 3 (CPD) / 7 (al día) | no | no |
  | 9 | — | usado en `020`/`010` cuando `FORMA_PAGO` es `MP`/`99` (real se informa aparte) |

  **Restricción del banco para `025`**: un Echeq (`EC`) en un registro `025`
  solo admite código 1, 2, 5 o 6 (debe ser "a la orden"); validado en el
  wizard antes de generar el archivo.
- **Tipo de documento** (`IDENTIFICATION_TYPE_BBVA`): traduce
  `document_type_id.name` de Odoo (`CUIT`/`CUIL`/`DNI`/`LE`/`LC`/`CDI`) al
  código BBVA (`CUI`/`CUL`/`DNI`/`LE`/`LC`/`CDI`).
- **Provincia** (`PROVINCE_CODE_BBVA`): diccionario fijo de 24 entradas,
  `res.country.state` (xmlid) → código BBVA de 2 dígitos; no hay
  correspondencia numérica entre ambos catálogos.

## 6. Validación contra archivos reales

Las posiciones/longitudes de los 5 registros están comprobadas carácter por
carácter contra 3 archivos reales del banco (en `docs/`, no versionados —
ver `.gitignore`):

- `JUMI_OP_ECHEQS_2026-06-23.txt`: 2 órdenes, cada una con un solo Echeq (sin
  registro `025`).
- `IMPA_OP_ECHEQS_2026-06-23 copy.txt`: 3 órdenes, una de ellas (minuta
  `00000698`) cancelada con 4 Echeqs → 4 registros `025`.
- `LUFRAN_OP_ECHEQS_2026-06-23.txt`: caso análogo con 7 instrumentos (minuta
  `00001679`).

Otro material de referencia en `docs/`:

- `ANALISIS_Y_DISENO.md` — análisis técnico completo (contexto, puntos
  abiertos, arquitectura propuesta, y el volcado íntegro de la especificación
  oficial del banco, incluidos los registros fuera de alcance).
- `matriz_campos_bbva.csv` / `Analisis_campos_TXT_BBVA_JUMI_obligatoriedad.xlsx`
  — Excel del cliente con los 128 campos de los registros 010/020/090/095.
- `Analisis_registro_025_BBVA_IMPA.xlsx` — análisis específico del registro
  `025`, con posiciones/longitudes/ejemplos extraídos del caso real IMPA.
- `BBVA DDRR Pago a Proveedores.docx.pdf` — especificación oficial del banco
  (59 páginas, todos los tipos de registro).

## 7. Pendiente / puntos abiertos

No bloquean el uso actual, pero quedan sin resolver:

1. **`PRO_NRO_BENEFICIARIO`/`PRO_NRO_BENEF`**: hoy se usa el `id` interno del
   partner. El banco no impone un criterio (correlativo por archivo vs.
   identificador estable), pero conviene confirmarlo con el cliente.
2. **Datos de cuenta de débito y contrato** (`SUC_CTA_DEBITO`,
   `DV_CTA_DEBITO`, `NRO_CTA_DEBITO`, `CONTRATO_PROV`): se piden a mano en
   cada ejecución del wizard. Convendría que vivan en una configuración
   persistente ligada al `account.journal`.
3. **Sin trazabilidad ni guard anti-doble-exportación**: no hay un modelo
   que registre qué órdenes ya se exportaron en un lote, ni un mecanismo de
   anulación manual (ver secciones 6.4/6.5 de `ANALISIS_Y_DISENO.md`).
4. **Transferencias (`FORMA_PAGO=AB`)** y los registros de facturas/
   retenciones (`030`/`040`/`060`/`070`/`080`) no están implementados — el
   alcance actual es exclusivamente cheques/Echeqs.
5. **Autorizados a retirar cheque físico** (`PRO_AUTORIZA_*` del `090`,
   obligatorio si `FORMA_PAGO=CH`) no tiene campo equivalente en Odoo hoy;
   sin impacto mientras el cliente solo emita Echeq.
