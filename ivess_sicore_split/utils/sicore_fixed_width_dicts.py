"""T16639: layout SICORE corregido segun el archivo de referencia del
cliente, sin modificar l10n_ar_eynes.

Diferencias contra odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width_dicts:
- numero_comprobante, monto_comprobante, base_calculo, importe_retencion,
  numero_documento_retenido y numero_certificado_original pasan de
  alineados a derecha (con ceros) a alineados a izquierda (con espacios):
  el cliente espera el dato "pegado" a la izquierda y el resto del campo
  en blanco, no rellenado con ceros.
- Se agrega HEAD_LINES_LOCAL, que suma un campo de relleno (posiciones
  146-198) para que el archivo local llegue a los 198 caracteres pedidos.
  El archivo de exterior no lo necesita: ya llega a 198 con sus propios
  campos (denominacion_ordenante, acrecentamiento, cuit_pais_retenido,
  cuit_ordenante).
"""

import copy

from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width_dicts import (
    HEAD_LINES as BASE_HEAD_LINES,
)
from odoo.addons.l10n_ar_eynes.utils.sicore_fixed_width_dicts import (
    HEAD_LINES_EXTERIOR as BASE_HEAD_LINES_EXTERIOR,
)

_FIELD_OVERRIDES = {
    "numero_comprobante": {
        "type": "string",
        "alignment": "left",
        "padding": " ",
    },
    "monto_comprobante": {"alignment": "left"},
    "base_calculo": {"alignment": "left"},
    "importe_retencion": {"alignment": "left"},
    "numero_documento_retenido": {"alignment": "left", "padding": " "},
    "numero_certificado_original": {"alignment": "left", "padding": " "},
}


def _with_overrides(base_config):
    config = copy.deepcopy(base_config)
    for field_name, changes in _FIELD_OVERRIDES.items():
        config[field_name].update(changes)
    return config


HEAD_LINES = _with_overrides(BASE_HEAD_LINES)
HEAD_LINES_EXTERIOR = _with_overrides(BASE_HEAD_LINES_EXTERIOR)

HEAD_LINES_LOCAL = {
    **HEAD_LINES,
    "relleno": {
        "type": "string",
        "start_pos": 146,
        "length": 53,
        "alignment": "left",
        "padding": " ",
        "required": False,
        "default": "",
    },
}
