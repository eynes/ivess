# ivess_webservice

Módulo Odoo 19 para la integración entre el middleware de Ivess y Odoo.

Expone métodos `@api.model` consumibles vía la External JSON-2 API de Odoo
(`POST /json/2/<model>/<method>`) con el contrato JSON acordado con el
middleware, y centraliza la lógica de notificación Odoo → middleware para
los flujos bidireccionales.

## Instalación

Este módulo se distribuye vía Doodba: se referencia desde el `repos.yaml`
del proyecto Ivess (rama `19.0`) y se habilita en `addons.yaml`.
