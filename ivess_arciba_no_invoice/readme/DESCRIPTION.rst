T16864.

El exportador eARCIBA (wizard "Create e-arciba Files") rechazaba con el error
"Unable to get associated invoice" las retenciones de las ordenes de pago sin
facturas imputadas (pagos a cuenta), y ese error bloqueaba la generacion de todo
el archivo.

Este modulo quita ese rechazo: la retencion se informa igual, usando el importe
de la orden de pago como total del comprobante cuando no hay lineas de deuda.
Las facturas no aportan ningun dato al registro (el IVA queda en 0.0 y la letra
del comprobante vacia), por lo que no cambia nada para las OP que si las tienen.
