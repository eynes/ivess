# Banco Nación Payment Order Export

Módulo de Odoo 19 que agrega un wizard para generar el archivo **CSV de
transferencias masivas a proveedores** de Banco Nación, a partir de las
órdenes de pago (`account.payment.order`, modelo propio de `l10n_ar_eynes`).

## 1. Formato del archivo

CSV separado por `;`, con encabezado obligatorio, en este orden exacto de
columnas:

```
CBU_CREDITO;IMPORTE;CONCEPTO;REFERENCIA;EMAIL
1254852125485212585254;1.270,00;FAC;pruebabna;grandesclientes@ausa.com.ar
```

| Columna | Origen en Odoo | Tratamiento |
|---|---|---|
| `CBU_CREDITO` | `res.partner.cbu` (campo agregado por `partner_vendor_custom`) | 22 dígitos, texto plano |
| `IMPORTE` | suma de `payment_mode_line_ids` cuyo `payment_mode_id` es el diario Banco Nación elegido en el wizard | formato decimal con coma (`1270.0` → `"1.270,00"`) |
| `CONCEPTO` | nuevo campo `concepto_bna` en la orden | código de 3 caracteres |
| `REFERENCIA` | `account.payment.order.reference` | normalizada: se quitan espacios y caracteres no alfanuméricos, máximo 12 caracteres |
| `EMAIL` | `res.partner.email` | opcional, puede ir vacío |

## 2. Nuevo campo: Concepto Banco Nación

`concepto_bna` (Selection) en `account.payment.order`, visible en el
formulario de órdenes de pago a proveedores. Valores admitidos:

| Código | Descripción |
|---|---|
| `VAR` | Varios |
| `ALQ` | Alquileres |
| `CUO` | Cuotas |
| `EXP` | Expensas |
| `FAC` | Factura (valor por defecto) |
| `PRE` | Préstamo |
| `SEG` | Seguros |
| `HON` | Honorarios |

No es de texto libre: al ser una selección, es imposible guardar un código
no admitido por el banco. No es obligatorio a nivel de modelo (no todas las
órdenes se pagan por Banco Nación); la obligatoriedad se valida solo al
exportar.

## 3. Cómo se identifica el importe "Banco Nación" de cada orden

Una orden de pago puede combinar varios métodos (efectivo, cheques,
retenciones, transferencia, pagos parciales). El importe a exportar **no**
es el total bruto de la orden: es la suma de sus líneas de
`payment_mode_line_ids` (`account.payment.mode.line`) cuyo `payment_mode_id`
es el diario/cuenta de Banco Nación. Ese diario se elige a mano en el
wizard, cada vez que se exporta (mismo criterio que el módulo hermano
`bbva_payment_order_export`, que tampoco persiste los datos del banco).

## 4. Flujo de uso

1. Menú *Contabilidad → Cuentas a pagar → Exportar a Banco Nación* (o acción
   contextual sobre el listado de órdenes de pago).
2. Elegir compañía, una o varias órdenes de pago (`type='payment'`,
   `state='posted'`) y el diario/cuenta de Banco Nación.
3. *Previsualizar*: arma el CSV completo en memoria y lo muestra en el
   propio wizard, sin generar ningún adjunto.
4. *Descargar CSV*: arma el archivo, lo sube como `ir.attachment` del
   wizard y dispara la descarga. Nombre:
   `BancoNacion_Transferencias_<Compañía>_<fecha>.csv`.

## 5. Validaciones

Antes de generar el archivo (`_check_payment_orders`) se valida, acumulando
todos los errores encontrados por orden antes de bloquear:

- Cada orden debe ser de la compañía elegida, tipo `payment` y estado
  `posted` (se bloquean explícitamente órdenes en `draft`/`cancel`/`proforma`).
- Debe tener proveedor asignado.
- El proveedor debe tener CBU informado y con exactamente 22 dígitos
  numéricos.
- Debe tener al menos una línea de pago con el diario Banco Nación elegido,
  y la suma de esas líneas debe ser mayor a cero.
- Debe tener un `concepto_bna` seleccionado y válido.
- La `reference`, una vez normalizada (sin espacios ni caracteres
  especiales), no puede estar vacía ni superar los 12 caracteres.
- El email **no** se valida: es opcional y puede exportarse vacío.
