"""Validacion de parametros del servicio ivess.operation.delivery.

Solo Python: nada de env ni ORM. Los productos se reciben ya buscados y
solo se leen sus atributos.
"""

# Cabecera basica: obligatoria en cualquier operacion.
BASIC_HEADER_SCHEMA = {
    "usuario_reparto": str,
    "fecha_operacion": str,
    "nro_reparto": int,
    "hora_atencion": str,
    "hora_envio": str,
    "codigo_cliente": str,
    "motivo_no_compra": int,
    "longitud": str,
    "latitud": str,
    "metros": (int, float),
    "fuera_ruta": bool,
}
# Caso venta (motivo_no_compra == 0).
SALE_SCHEMA = {
    "item_venta": list,
}
# Cada elemento de item_venta. Numericos aceptan int o float: en JSON un 2 llega como int.
SALE_ITEM_SCHEMA = {
    "codigo_producto": str,
    "cantidad": (int, float),
    "precio_venta": (int, float),
}
# Opcionales a nivel parametro: se validan contra el producto, no contra el esquema.
SALE_ITEM_OPTIONAL = {"tipo_venta", "series"}
# Valor de la app -> water.container.state.
CONTAINER_STATE_BY_TIPO_VENTA = {
    "V": "en_comodato",
    "P": "prestado",
}
# Categorias de error de parametros. El orden es la prioridad: se informa
# solo la primera categoria que tenga detalles.
PARAM_ERROR_MESSAGES = {
    "unknown": "Parametros no reconocidos",
    "missing": "Faltan parametros obligatorios",
    "invalid_type": "Tipo invalido en parametros",
    "not_applicable": "Parametros no aplicables",
    "invalid_value": "Valor invalido en parametros",
}


class ParamErrors:
    """Acumula los errores de parametros por categoria."""

    def __init__(self):
        self.details = {category: [] for category in PARAM_ERROR_MESSAGES}

    def __bool__(self):
        return any(self.details.values())

    def add(self, category, detail):
        self.details[category].append(detail)

    def extend(self, other):
        for category, details in other.details.items():
            self.details[category] += details

    def message(self):
        """Mensaje de la categoria de mayor prioridad con detalles, o None."""
        for category, text in PARAM_ERROR_MESSAGES.items():
            if self.details[category]:
                return "%s: %s" % (text, ", ".join(self.details[category]))
        return None


def requires_container_state(product):
    """El estado de envase (tipo_venta) solo aplica a retornables que no son frio/calor."""
    return product.is_returnable and not product.is_frio_calor


def check_schema(params, schema, errors, prefix=""):
    """Valida params contra schema ({param: tipo | tupla de tipos}) y
    carga los faltantes y tipos invalidos en errors.
    Solo revisa las keys del schema; las desconocidas se controlan aparte."""
    for param, expected_types in schema.items():
        if not isinstance(expected_types, tuple):
            expected_types = (expected_types,)
        value = params.get(param)
        if value is None or value == "" or value == []:
            errors.add("missing", prefix + param)
        # type() y no isinstance(): bool es subclase de int
        elif type(value) not in expected_types:
            errors.add("invalid_type", "%s%s (%s)" % (
                prefix, param, "/".join(t.__name__ for t in expected_types),
            ))


def validate_header(params):
    """Fase 1: cabecera basica. Va primero porque motivo_no_compra define
    el caso y, por ende, que otros parametros se esperan."""
    errors = ParamErrors()
    check_schema(params, BASIC_HEADER_SCHEMA, errors)
    return errors


def validate_case_params(params, case_schema):
    """Fase 2: parametros propios del caso (hoy, item_venta y cada item)."""
    errors = ParamErrors()
    check_schema(params, case_schema, errors)
    if type(params.get("item_venta")) is list:
        for index, item in enumerate(params["item_venta"]):
            if type(item) is not dict:
                errors.add("invalid_type", "item_venta[%s] (dict)" % index)
                continue
            prefix = "item_venta[%s]." % index
            unknown_keys = set(item) - set(SALE_ITEM_SCHEMA) - SALE_ITEM_OPTIONAL
            for param in sorted(unknown_keys):
                errors.add("unknown", prefix + param)
            item_errors = ParamErrors()
            check_schema(item, SALE_ITEM_SCHEMA, item_errors, prefix)
            errors.extend(item_errors)
            tipo_venta = item.get("tipo_venta")
            if tipo_venta is not None:              # caso de productos retornables, requieren tipo_venta
                if type(tipo_venta) is not str:
                    errors.add("invalid_type", prefix + "tipo_venta (str)")
                elif tipo_venta not in CONTAINER_STATE_BY_TIPO_VENTA:
                    errors.add("invalid_value", prefix + "tipo_venta (%s)" % "/".join(CONTAINER_STATE_BY_TIPO_VENTA))
            series = item.get("series")
            if series is not None:                  # caso de productos con seguimiento por numero de serie, requieren series
                if type(series) is not list:
                    errors.add("invalid_type", prefix + "series (list)")
                else:
                    for serie_index, serie in enumerate(series):
                        if type(serie) is not str or not serie.strip():
                            errors.add("invalid_type", "%sseries[%s] (str)" % (prefix, serie_index))
            if item_errors:
                continue
            if item["cantidad"] <= 0:
                errors.add("invalid_value", prefix + "cantidad (> 0)")
            if item["precio_venta"] < 0:
                errors.add("invalid_value", prefix + "precio_venta (>= 0)")
    return errors


def validate_tipo_venta(item_venta, products_by_code):
    """tipo_venta: obligatorio solo en productos que requieren estado de envase."""
    errors = ParamErrors()
    for index, item in enumerate(item_venta):
        product = products_by_code[item["codigo_producto"]]
        has_tipo_venta = item.get("tipo_venta") is not None
        if requires_container_state(product) and not has_tipo_venta:
            errors.add("missing", "item_venta[%s].tipo_venta (%s es retornable)" % (index, product.default_code))
        elif not product.is_returnable and has_tipo_venta:
            errors.add("not_applicable", "item_venta[%s].tipo_venta (%s no es retornable)" % (index, product.default_code))
    return errors


def validate_series(item_venta, products_by_code):
    """series: obligatoria (una por unidad) solo con seguimiento por numero de serie.
    Devuelve (errors, requested_series) con requested_series = {(product_id, serie)}."""
    errors = ParamErrors()
    requested_series = set()
    for index, item in enumerate(item_venta):
        product = products_by_code[item["codigo_producto"]]
        series = item.get("series") or []
        prefix = "item_venta[%s]." % index
        if product.tracking != "serial":
            if series:
                errors.add("not_applicable", prefix + "series (%s no tiene seguimiento por serie)" % product.default_code)
            continue
        if not series:
            errors.add("missing", prefix + "series (%s tiene seguimiento por serie)" % product.default_code)
            continue
        if not float(item["cantidad"]).is_integer() or len(series) != item["cantidad"]:
            errors.add("invalid_value", prefix + "series (una serie por unidad: cantidad entera igual a %s series)" % len(series))
        for serie in series:
            if (product.id, serie) in requested_series:
                errors.add("invalid_value", prefix + "series (%s repetida)" % serie)
            requested_series.add((product.id, serie))
    return errors, requested_series
