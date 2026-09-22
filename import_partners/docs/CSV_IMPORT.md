# Importación CSV de partners — Odoo 19 / Doodba

Este flujo usa `res.partner.csv.import.run` desde **Odoo shell**. No usar el wizard
Excel anterior: ese wizard inserta por SQL y no implementa este flujo.

## Subir los CSV sin SSH/SFTP

En entornos donde no hay acceso directo por SSH/SFTP al filesystem del servidor
(por ejemplo odoo.sh sin la clave SSH configurada), el wizard **"Subir CSV de
importación de partners"** (Contactos → Configuración) permite subir los 3
archivos desde el navegador. Guarda cada uno con su nombre esperado en
`res.partner.csv.import.run._csv_dir()` — una carpeta dentro de `data_dir`,
identificada por el nombre de la base (`<data_dir>/csv_import/<dbname>/`) — y
corre la validación estructural (`csv_source.load()`, sin tocar la base) para
confirmar de inmediato que los archivos subidos son legibles y tienen el
formato esperado. **Solo sube y valida; no ejecuta el import.** La corrida real
se sigue disparando desde Odoo shell como el resto de esta guía, y por defecto
usa esa misma carpeta cuando no se pasa `PARTNER_CSV_DIR` explícitamente.

## Inspección y decisiones

- Doodba: `docker-compose.yml -> devel.yaml`; PostgreSQL 17, Odoo 19.
- `logistic_custom_ivess`: códigos, indicadores cliente/proveedor (inversas sobre
  ranks), celular, tipos de cliente, horarios y restricciones logísticas.
- `ivess_partner_custom`: código Bejerman único por compañía mediante constraint
  Python, fecha de alta y restricciones al archivar.
- `l10n_ar_eynes`: documento, CUIT, duplicación documental y propiedades fiscales.
- `partner_vendor_custom`: proveedor requiere email.
- `pricelist_custom`: precios especiales.
- `l10n_ar_padron_ws_consumer` / `ivess_padron_error_handling`: consulta externa al
  crear; se omite únicamente con el contexto privado de esta importación.
- Odoo exige valores para `autopost_bills`, `group_rfq`, `group_on`; el ORM aplica
  sus defaults. El importador exige además nombre, compañía y clave de origen.

Los tres CSV son UTF-8, delimitador `;`, 34 encabezados idénticos. Se preservan
ceros iniciales en códigos. `NULL`, blancos y espacios se normalizan; los datos
originales se conservan en los reportes. Las coordenadas ya tienen punto decimal:
no se inserta un punto artificialmente.

| Archivo | Filas | Compañía |
|---|---:|---|
| page_clientes_jumillano.csv | 133.056 | El Jumillano S.A., 1 |
| page_clientes_lufran.csv | 20.848 | Lufrán S.A., 8 |
| page_ctas_madres_hijas_all.csv | 2.364 | Empresa: 2.124 de 1; 240 de 8 |
| Total | 156.268 | |

El archivo jerárquico contiene 837 madres y 1.527 hijas. `nrosub` de la hija apunta
al **Código de Cliente de la madre**, dentro de la misma compañía; las madres no
tienen nrosub. Quedan 5 hijas rechazadas como `missing_or_rejected_mother`: 2 cuya
madre existe pero con una Empresa distinta a la de la hija (verificado y rechazado
explícitamente, no aceptado) y 3 huérfanas reales cuyo `nrosub` no corresponde a
ninguna madre del archivo. Es la única categoría de rechazo restante del preflight
sobre este archivo. No hay claves repetidas en los otros dos archivos ni
colisiones entre ellos.

Clave idempotente: `(company_id, codigo_bejerman)` para madres y contactos
autónomos; Bejerman vacío/NULL/0 usa `SC-<customer_code>`. Confirmado: el
Código Bejerman del CSV **solo identifica a la madre**; toda hija (cualquier
fila con `nrosub`) queda con `codigo_bejerman` vacío en Odoo, sin importar qué
traiga su propia columna Bejerman en el CSV — nunca se le asigna un valor, ni
siquiera el fallback `SC-`. El constraint de `ivess_partner_custom` no valida
Bejerman vacío (`if not partner.codigo_bejerman: continue`), así que ninguna
hija colisiona con otra por eso. Cada hija se identifica y actualiza en
corridas repetidas por su propio `customer_code` en vez de por Bejerman (ver
`_apply_row`). Esto eliminó los 572 rechazos `duplicate_key` que existían antes
en este archivo (una madre podía colisionar con una hija que repetía su
código), incluida una madre con 101 hijas (MUNICIPALIDAD PARTIDO 3 DE FEBRERO).
Nunca se usa nombre o CUIT como identificador: muchas hijas comparten CUIT y
`NOIMPORTADO` no identifica un contacto. Un `customer_code` ya existente con
otro Bejerman se rechaza para revisión; no se cambia su identidad. Partners
compartidos (company_id vacío) y coincidencias múltiples se rechazan.
Se incluyen archivados y no se reactivan automáticamente.

Confirmado: si una hija figura con una Empresa distinta a la de su madre en el
CSV, no es un vínculo válido. `nrosub` se verifica explícitamente contra la
compañía de la hija (no solo contra su Código de Cliente); si no coincide, la
fila se rechaza como `missing_or_rejected_mother` igual que una madre ausente,
en vez de aceptarse silenciosamente. Casos actuales: fila 752 (DUOPACK SRL,
Lufrán) cuya madre en fila 753 pertenece a El Jumillano S.A., y fila 1490 (MARIA
MARCELA RANDAZZO SBARBO, Lufrán) cuya madre en fila 1492 pertenece a El
Jumillano S.A.

## Mapeo

| CSV | Odoo / tratamiento |
|---|---|
| Nombre | name |
| Código de Cliente | customer_code |
| Código Bejerman | codigo_bejerman; fallback SC-. En madres/hijas solo se usa en la madre: toda hija queda vacía, identificada por customer_code |
| Es Cliente / Es Proveedor | is_customer / is_supplier vía sus inversas |
| nrosub | parent_id, búsqueda por código cliente madre (cualquier compañía) |
| Tipo de empresa | company_type: EMPRESA→company, PERSONA→person |
| Correo electronico | email |
| Teléfono / Numero de Celular | phone / mobile_number; conserva el texto, incluso errores y notación científica; solo advierte |
| Calle / Ciudad | street / city |
| País | country_id, Argentina por XML ID base.ar |
| Estado | state_id, nombre normalizado y país AR |
| Tipo de Documento | document_type_id, res.document.type |
| NrCUIT | vat; control DNI/CUIT/CUIL; inválido/vacío → NOIMPORTADO y Doc. (Otro), reportado |
| Cliente Importante | is_important_client |
| Fecha de Alta | fecha_alta, conserva hora literal del origen; no modifica create_date |
| Precios Especiales | has_special_price |
| Posición fiscal | property_account_position_id, compañía correcta |
| Tipo de cliente | partner_type_id, client.type.description |
| Requiere Comprobante | requiere_comprobante |
| Geo latitud / Geo longitud | partner_latitude / partner_longitude, límites geográficos |
| Etiqueta | category_id, comando ORM m2m set |
| Horario promedio | average_hour, HH:MM a horas decimales |
| Empresa | company_id, valida ID y nombre antes de comenzar |
| Términos de pago del cliente | property_payment_term_id; CONTADO → Pago inmediato - Contado (1), CTA. CORRIENTE → CTA CTE (25), confirmado |
| ListaPrecio | Se ignora. property_product_pricelist usa la lista predeterminada de la compañía S.A. destino |
| Distribuciones / Días / Zona venta / Observaciones de Direccion / Cuenta por Cobrar | Excluidos por confirmación funcional; no se sobrescriben |

Solo se admiten las compañías El Jumillano S.A. (1) y Lufrán S.A. (8). Se tolera
Lufran sin tilde en fuentes/base; nunca se confunden con El Jumillano o Lufrán sin
S.A. La lista se resuelve con el mecanismo estándar de Odoo para Argentina, bajo
`with_company()` y validando que esté activa y pertenezca a la compañía destino.
No se buscan listas por nombre del CSV ni se crean listas. Si no hay una lista
predeterminada válida para esa S.A., se detiene el preflight. También se reemplaza
la lista de clientes existentes no proveedores por la predeterminada de su compañía.

Los campos mapeados vacíos limpian el valor anterior (las propiedades pueden mostrar
el default de Odoo). Las etiquetas se reemplazan. Proveedores existentes no se
escriben, aunque el CSV diga que no son proveedores. Se protege también la familia
comercial cuando la sincronización ORM podría afectar a un proveedor. Una fila
nueva marcada proveedor sin email pasa a no proveedor y deja advertencia.

Confirmado: hijas con `type='other'` para preservar su dirección, conservando
company_type del CSV. El indicador `csv_inherit_commercial` hace que hereden
commercial_partner_id incluso siendo empresas. Los campos comerciales gestionados
por la madre (documento, CUIT, propiedades contables y lista) se toman de ella para
no sobrescribirla desde una hija; las diferencias quedan reportadas. La extensión
no cambia el cómputo de los demás contactos.

## Ejecución local

Desde la raíz del proyecto, con la base local restaurada y sin trabajadores que
escriban partners durante la carga. El lock asesor impide importadores simultáneos;
no bloquea ediciones manuales ni integraciones ajenas al importador. Respaldar base
y filestore antes de aplicar en un entorno que deba conservarse.

Crear una copia de prueba nueva (no sobreescribir una copia existente):

```bash
docker compose -f devel.yaml exec -T db createdb -U odoo -T devel devel_partner_import_test
```

Actualizar módulo y ejecutar tests solo en esa copia:

```bash
docker compose -f devel.yaml run --rm --no-deps -T odoo \
  odoo -d devel_partner_import_test -u import_partners --stop-after-init \
  --no-http --max-cron-threads=0 --test-enable --test-tags /import_partners
```

Validación estructural completa, sin Odoo:

```bash
python odoo/custom/src/modules/import_partners/csv_source.py "$PWD/SRC"
```

Validación completa de valores y relaciones (solo lectura):

```bash
docker compose -f devel.yaml run --rm --no-deps -T \
  -v "$PWD/SRC:/input:ro" -e PARTNER_CSV_DIR=/input odoo \
  odoo shell -d devel_partner_import_test --no-http --max-cron-threads=0 \
  < odoo/custom/src/modules/import_partners/scripts/validate_csv.py
```

Dry-run de 1.000 filas por CSV (3.000 en total); ejecuta create/write y revierte la transacción:

```bash
docker compose -f devel.yaml run --rm --no-deps -T \
  -v "$PWD/SRC:/input:ro" -e PARTNER_CSV_DIR=/input \
  -e PARTNER_IMPORT_DB=devel_partner_import_test \
  -e PARTNER_IMPORT_PER_FILE=1000 -e PARTNER_IMPORT_BATCH=100 odoo \
  odoo shell -d devel_partner_import_test --no-http --max-cron-threads=0 \
  < odoo/custom/src/modules/import_partners/scripts/run_csv.py
```

Para aplicar la misma prueba, agregar `-e PARTNER_IMPORT_APPLY=yes`. El nombre de base
se verifica contra `PARTNER_IMPORT_DB`. Tanto `run_csv.py` como `test_real_sample.py`
usan **1.000 filas por cada archivo** por defecto. El cupo incluye rechazados y
proveedores protegidos: no significa 1.000 altas exitosas por archivo.

`PARTNER_IMPORT_PER_FILE=0` en `run_csv.py` habilita el conjunto completo;
`test_real_sample.py` exige un cupo positivo para evitar una carga completa accidental.
`PARTNER_IMPORT_LIMIT` es un límite global adicional por invocación, por defecto 0
(sin límite adicional), útil para pausar/reanudar. No usarlo para definir el tamaño
por archivo. `PARTNER_IMPORT_BATCH` controla commits (100 en la prueba representativa,
500 por defecto en `run_csv.py`); cada fila usa ORM y savepoint.

`PARTNER_IMPORT_EXCLUDE` (opcional, `run_csv.py` y `validate_csv.py`) rechaza filas
puntuales antes del preflight, sin editar el CSV ni el código: lista de `archivo:línea`
separada por comas, por ejemplo
`PARTNER_IMPORT_EXCLUDE=page_ctas_madres_hijas_all.csv:697,page_ctas_madres_hijas_all.csv:424`.
Quedan con `error=excluded_by_operator` y cuentan en `rejected` del resumen; si la fila
excluida era una madre, sus hijas caen en cascada con `error=mother_excluded_by_operator`
(distinto de `missing_or_rejected_mother`, reservado a madres realmente ausentes del
CSV) — permite avisar al cliente exactamente qué contactos se saltearon a propósito,
sin confundirlos con huérfanas reales. Cambiar el conjunto de exclusión cambia el
fingerprint: no se puede reanudar una corrida con una lista distinta a la que empezó.

Para armar el aviso al cliente sin correr Odoo, `csv_source.py` acepta `--exclude` y
además del resumen imprime la lista completa (excluidas directas + hijas en cascada)
con línea, código de cliente, nombre y motivo:

```bash
python odoo/custom/src/modules/import_partners/csv_source.py "$PWD/SRC" \
  --exclude "page_ctas_madres_hijas_all.csv:697,page_ctas_madres_hijas_all.csv:424,page_ctas_madres_hijas_all.csv:1413,page_ctas_madres_hijas_all.csv:1517"
```

La selección se hace sobre el preflight completo y conserva errores globales y
números de registro del CSV original. Se recorre el orden original de cada archivo;
una hija válida reserva también un lugar para su madre, dentro del mismo cupo. Si
no hay espacio para ambas, se considera la siguiente fila. Se exige alcanzar el
cupo exacto en los tres archivos; si falta material, se aborta antes de escribir.
El procesamiento ordena madres antes que hijas. No se generan CSV recortados que
puedan ocultar duplicados presentes fuera de la muestra.

Cada lote guarda reporte, checkpoint, contadores totales y contadores **por archivo**
en la misma transacción. Para reanudar se requieren los mismos archivos y el mismo
`PARTNER_IMPORT_PER_FILE`; cambiar el cupo cambia la huella de la ejecución.

Prueba transaccional adicional, con commits reales y datos sintéticos en la copia:

```bash
docker compose -f devel.yaml run --rm --no-deps -T odoo \
  odoo shell -d devel_partner_import_test --no-http --max-cron-threads=0 \
  < odoo/custom/src/modules/import_partners/scripts/test_transactions.py
```

## Recuperación y reportes

- Anotar `run_id` del resumen. Si el proceso se corta antes del resumen, buscar
  `env['res.partner.csv.import.run'].search([], order='id desc', limit=1)` en shell.
- Repetir el comando apply con `-e PARTNER_IMPORT_RUN=<id>`, los mismos tres archivos
  y la misma versión. SHA-256 de archivos y versión del formato impide reanudar
  entradas alteradas. El último lote confirmado no se reprocesa.
- Una excepción inesperada aborta el lote; no se transforma en miles de rechazos.
  Corregir la causa y reanudar. Errores de datos/constraints se aíslan por savepoint.
- Las madres rechazadas se guardan con el checkpoint, para no adjuntar hijas a una
  versión antigua de una madre que no se pudo actualizar.
- Para reintentar rechazados, corregir fuentes/relaciones y crear una ejecución
  nueva. La idempotencia evita duplicar lo ya importado. No cambiar checkpoint a mano.
- Los archivos están en `ir.attachment`, `res_model='res.partner.csv.import.run'`,
  `res_id=<run_id>`. Cada fila reportada contiene archivo, número de registro CSV,
  estado, motivo y los 34 valores originales. Incluye advertencias y proveedores
  protegidos. Celdas peligrosas para planillas llevan un apóstrofo de protección.
- Descarga autenticada: `/web/content/<attachment_id>?download=true`. Acceso del
  registro de ejecución limitado a administradores. No publicar reportes con datos
  personales. Exportar desde shell con `base64.b64decode(attachment.datas)`.
- Dry-run no persiste partners, reportes ni checkpoints; devuelve incidencias en JSON.
  Guardar stdout o usar `PARTNER_IMPORT_RESULT` con un directorio de salida montado.
  Las secuencias PostgreSQL pueden consumir IDs incluso cuando se hace rollback.
- Una importación confirmada no tiene «undo» automático: recuperar mediante backup
  completo o una corrección revisada. Reanudar no revierte lotes anteriores.

## Operación y límites

El parser realiza un preflight global en memoria para detectar duplicados incluso
fuera del límite de prueba; reservar memoria para las 156k filas, no solamente para
el lote. Para dry-run completo también se acumula la transacción; preferir muestras
representativas y la validación completa de solo lectura antes de aplicar.
Hay índices ORM en customer_code y codigo_bejerman; no se usa SQL para insertar ni
actualizar partners. SQL propio solo toma/libera el lock asesor.

No se han ejecutado cargas en producción. Promover el mismo commit y archivos
validados a staging, repetir validación/dry-run/muestra y revisar rechazos. Antes de
producción verificar compañías, relaciones, versiones instaladas, copia recuperable
y ventana sin escrituras concurrentes; ejecutar explícitamente con el nombre de esa
base. No reutilizar un run_id entre bases.

La copia restaurada emite avisos de módulos/tablas ajenos al importador faltantes
(account_financial_report, esg_csrd y algunos reportes ivess, entre otros). Los tests
del importador no certifican esos módulos ni equivalencia completa con producción.

## Validación actual y cambio de criterio

Se reemplazó la política anterior de buscar ListaPrecio del CSV por la instrucción
confirmada de usar la lista predeterminada de cada S.A. El inventario
`required_pricelists.csv` queda como referencia histórica; no representa catálogos
pendientes de cargar. La versión de preflight es 12: las ejecuciones anteriores no
pueden reanudarse con esta política; iniciar una ejecución nueva.

La versión 11 agregó `PARTNER_IMPORT_EXCLUDE` (ver arriba, sección "Ejecución local")
para saltear filas puntuales por operador sin tocar el CSV; el conjunto de exclusión
pasó a formar parte del fingerprint reanudable.

La versión 12 le dio a la cascada de hijas de una madre excluida su propio motivo,
`mother_excluded_by_operator`, separado de `missing_or_rejected_mother` (reservado a
madres realmente ausentes del CSV), y agregó `--exclude` al CLI de `csv_source.py`
para listar excluidas directas + cascada sin correr Odoo.

La versión 6 había relajado la vinculación madre/hija para aceptar una Empresa
distinta entre ambas (la hija conservaba su propia Empresa). La versión 9 revirtió
esa decisión: ahora la compañía de la madre se verifica explícitamente contra la
de la hija y, si difieren, se rechaza como `missing_or_rejected_mother` en vez de
aceptarse. Casos actuales en `page_ctas_madres_hijas_all.csv`: filas 752/753
(DUOPACK SRL) y 1490/1492 (MARIA MARCELA RANDAZZO SBARBO).

La versión 7 corrigió el caso en que una hija repite el Código Bejerman literal
de su madre: antes colisionaba con la madre bajo `(company_id, codigo_bejerman)`
y ambas se rechazaban como `duplicate_key`, arrastrando en cascada al resto de
las hijas de esa madre.

La versión 8 confirmó y generalizó la regla anterior (ver "Clave idempotente"):
el Código Bejerman del CSV solo identifica a la madre; ahora **toda** hija usa
`SC-<customer_code>`, tenga o no el mismo Bejerman que su madre. Esto eliminó
los `duplicate_key` de `page_ctas_madres_hijas_all.csv` (las versiones 7 y 8
juntas los bajaron de 572 a 0).

Con la versión 9, `page_ctas_madres_hijas_all.csv` rechaza 5 filas como
`missing_or_rejected_mother`: 2 por Empresa distinta entre madre e hija (fila
752/753 y 1490/1492) y 3 huérfanas reales sin madre en el CSV (filas 912, 1546
y 1640; pendientes de revisión, no bloquean el resto de la importación).

La versión 10 confirmó y simplificó la regla del Bejerman: ya no se le asigna
`SC-<customer_code>` a las hijas (introducido en la versión 8), sino que
`codigo_bejerman` queda directamente vacío en Odoo para cualquier fila con
`nrosub`. El constraint de `ivess_partner_custom` no valida Bejerman vacío, así
que no hay colisión entre hijas de una misma compañía. Como el campo ya no
sirve para identificarlas, `_apply_row` busca y actualiza cada hija por su
propio `customer_code` en vez de por `codigo_bejerman`; las madres y los
contactos autónomos de `page_clientes_*` no cambian.

Los CSV se encuentran actualmente en `SRC/` de la raíz del proyecto. Los resultados
actuales se guardan en `preflight.json`, `validation.json`, `sample_result.json` y
`test_results.json`. La validación informa el primer motivo de rechazo por fila.

Prueba representativa real (solo admite la copia `devel_partner_import_test`):

```bash
docker compose -f devel.yaml run --rm --no-deps -T \
  -v "$PWD/SRC:/input:ro" -e PARTNER_CSV_DIR=/input odoo \
  odoo shell -d devel_partner_import_test --no-http --max-cron-threads=0 \
  < odoo/custom/src/modules/import_partners/scripts/test_real_sample.py
```

Selecciona 1.000 filas de cada uno de los tres archivos (3.000 en total). Hace
dry-run, aplicación y repetición, y comprueba los resultados por archivo, las
listas por compañía, los teléfonos conservados y los vínculos madre/hija. La
segunda pasada debe terminar sin nuevas altas ni actualizaciones.

Los teléfonos y celulares no rechazan filas: se conserva el valor textual del
CSV después de la normalización general de espacios externos y NULL. No se eliminan
letras ni se convierte la notación científica a un número. Los formatos dudosos
quedan en el reporte con `phone_format_preserved:<columna>`; el estado de la fila
sigue siendo created, updated o unchanged. El resto de las validaciones permanece.

El cambio a selección por archivo usa versión 5. Iniciar una ejecución nueva para
la prueba de 1.000 por archivo; no reanudar ejecuciones anteriores. `validation.json`
conserva la validación completa de valores de la versión 4 (mismos archivos y reglas
de mapeo); `preflight.json` y `sample_result.json` describen la selección actual.

## Resultado de la prueba de 1.000 por archivo

Ejecutada en `devel_partner_import_test`, con dry-run, aplicación en lotes de 100
y repetición idempotente. Los resultados del dry-run coincidieron con la aplicación.

| CSV | Procesados | Creados | Sin cambios | Rechazados |
|---|---:|---:|---:|---:|
| Jumillano | 1.000 | 960 | 40 | 0 |
| Lufrán | 1.000 | 960 | 40 | 0 |
| Madres/hijas | 1.000 | 662 | 13 | 325 |
| Total | 3.000 | 2.582 | 93 | 325 |

Los 325 rechazos son 276 claves duplicadas y 49 madres ausentes/rechazadas. No hubo
rechazos por teléfonos. La repetición dejó 2.675 sin cambios y los mismos 325
rechazados; no creó ni actualizó partners. Se verificaron listas, teléfonos y
jerarquías de los 2.675 aceptados. La copia pasó de 7.337 a 9.919 partners antes
de las pruebas transaccionales sintéticas posteriores. Ejecución de aplicación
22; repetición 23. Los adjuntos y resultados por archivo están en `sample_result.json`.

16 tests Odoo aprobados. No se ejecutó la carga completa ni se modificó producción.

La prueba transaccional adicional también pasó: commits, rollback del dry-run,
interrupción, reanudación, contadores por archivo y bloqueo al cambiar el cupo.
