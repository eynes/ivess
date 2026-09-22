# ivess_webservice

Módulo Odoo 19 para la integración entre el middleware de Ivess y Odoo.

Expone métodos `@api.model` consumibles vía la External JSON-2 API de Odoo
(`POST /json/2/<model>/<method>`) con el contrato JSON acordado con el
middleware, y centraliza la lógica de notificación Odoo → middleware para
los flujos bidireccionales.

## Instalación

Este módulo se distribuye vía Doodba: se referencia desde el `repos.yaml`
del proyecto Ivess (rama `19.0`) y se habilita en `addons.yaml`.

## Servicios de intake del chatbot de WhatsApp (Meta Flows)

Los 4 servicios comparten usuario y API key del middleware ("Servicios Web
Ivess Usuario", login `ivess_wb_user`, grupo `Ivess Webservice User`) y la
misma respuesta OK: `{"success": true, "ticket_id": ..., "ticket_name": ...,
"already_registered": false, "warnings": []}`. Ante error devuelven
`{"error": "<mensaje>"}`. Todos soportan idempotencia opcional vía
`external_id` (si ya existe un ticket con ese id, no crean nada y devuelven
`already_registered: true`).

### `ivess.workshop.news.intake` — Novedades Taller

`POST /json/2/ivess.workshop.news.intake/create_ticket`

Requeridos: `dispatch`, `patente`, `observations`.
Opcionales: `attachments` (0 a 2, campo `image`), `partner_phone`, `external_id`.

### `ivess.breakdown.intake` — Auxilio

`POST /json/2/ivess.breakdown.intake/create_ticket`

Requeridos: `patente`, `dispatch`, `driver_name`, `vehicle_model`,
`vehicle_location`, `breakdown_reason`.
Opcionales: `description`, `latitude`/`longitude` (o `maps_location`),
`partner_phone`, `external_id`.
Acepta como alias los nombres del contrato viejo: `webhub_dispatch`,
`webhub_vehicle_model`, `webhub_description`, `partner_id` (éste último
pasa a `driver_name`).

### `ivess.accident.intake` — Siniestro

`POST /json/2/ivess.accident.intake/create_ticket`

Todos los parámetros son requeridos salvo `accident_notes`,
`partner_phone` y `external_id`: `business_unit`, `patente`, `dispatch`,
`driver_file_number`, `driver_name`, `driver_identification`,
`driver_address`, `vehicle_damage`, `facts_description`,
`third_party_name`, `third_party_vehicle`, `third_party_patente`,
`third_party_identification`, `third_party_phone`, `third_party_insurer`,
`third_party_vehicle_damage`, `accident_date` (`AAAA-MM-DD` o
`DD/MM/AAAA`), `accident_time` (`HH:MM`), `accident_address`,
`accident_city`, `attachments` (obligatorios: `company_vehicle`,
`third_party_vehicle`, `third_party_policy`, `third_party_license`,
`third_party_vehicle_card` de a 1, y `driver_license` de 1 a 2).

### `ivess.refill.intake` — Recarga

`POST /json/2/ivess.refill.intake/create_ticket`

No es un servicio de taller: crea el ticket en el equipo de helpdesk
`Recargas` (`team_type = refill`) y no genera orden de mantenimiento. Si
ese equipo no existe en la base, devuelve error.

Requeridos siempre: `refill_type` (`factory` o `street`), `dispatch`,
`request` (máx. 600 caracteres).
- `factory`: además requiere `vehicle_location`; no acepta `to_dispatch`.
- `street`: además requiere `to_dispatch` (no puede ser igual a `dispatch`).

Opcionales: `partner_phone`, `external_id`.

Requiere que el usuario del webservice tenga asignado el grupo
`helpdesk_maint_custom.group_helpdesk_refill` (se asigna a mano en prod,
no viene por datos del módulo).
