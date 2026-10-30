"""Validacion de parametros del servicio ivess.operation.delivery.

Solo Python: nada de env ni ORM. Los productos se reciben ya buscados y
solo se leen sus atributos.
"""
from dataclasses import dataclass

# Cabecera basica
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

# Venta de productos (motivo_no_compra == 0).
SALE_SCHEMA = {
    "item_venta": list,
}
SALE_ITEM_SCHEMA = {
    "venta_cod_producto": str,
    "venta_cantidad": (int, float),
    "venta_precio": (int, float),
}
SALE_ITEM_OPTIONAL = {"venta_tipo_envase", "venta_series"}

# Retiro de envases: se combina con una venta o con un motivo de no compra; nunca va solo.
WITHDRAWAL_SCHEMA = {
    "item_retiro": list,
}
WITHDRAWAL_ITEM_SCHEMA = {
    "retiro_cod_producto": str,
    "retiro_cantidad": (int, float),
}
WITHDRAWAL_ITEM_OPTIONAL = {"retiro_tipo_envase", "retiro_series"}

CONTAINER_STATE = {
    "V": "en_comodato",
    "P": "prestado",
}


@dataclass(frozen=True)
class ItemSpec:
    """Nombres de los campos de una lista de items. Venta y retiro se validan
    con las mismas reglas; solo cambian los nombres y si el tipo aplica a los
    frio/calor (strict_tipo)."""
    list_key: str
    code: str
    qty: str
    tipo: str
    series: str
    schema: dict
    optional: set
    price: str | None = None
    strict_tipo: bool = False


SALE_ITEMS = ItemSpec(
    "item_venta", 
    "venta_cod_producto", 
    "venta_cantidad", 
    "venta_tipo_envase", 
    "venta_series",
    SALE_ITEM_SCHEMA, 
    SALE_ITEM_OPTIONAL, 
    price="venta_precio",
)
WITHDRAWAL_ITEMS = ItemSpec(
    "item_retiro", 
    "retiro_cod_producto", 
    "retiro_cantidad", 
    "retiro_tipo_envase", 
    "retiro_series",
    WITHDRAWAL_ITEM_SCHEMA, 
    WITHDRAWAL_ITEM_OPTIONAL, 
    strict_tipo=True,
)
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
    """El estado de envase (venta_tipo_envase / retiro_tipo_envase) solo aplica a retornables que no son frio/calor."""
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


def case_param_names(params):
    """Parametros propios del caso: item_retiro siempre; item_venta solo cuando
    no hay motivo de no compra."""
    names = {WITHDRAWAL_ITEMS.list_key}
    if params["motivo_no_compra"] == 0:
        names.add(SALE_ITEMS.list_key)
    return names


def validate_case_params(params):
    """Fase 2: parametros propios del caso (item_venta, item_retiro y cada item).
    Sin motivo de no compra la visita es una venta: item_venta es obligatorio.
    item_retiro acompana a una venta o a una no compra; nunca va solo."""
    errors = ParamErrors()
    if params["motivo_no_compra"] == 0:
        check_schema(params, SALE_SCHEMA, errors)
    # item_retiro en null equivale a ausente; una lista vacia es faltante.
    if params.get(WITHDRAWAL_ITEMS.list_key) is not None:
        check_schema(params, WITHDRAWAL_SCHEMA, errors)
    for spec in (SALE_ITEMS, WITHDRAWAL_ITEMS):
        validate_items(params, spec, errors)
    return errors


def validate_items(params, spec, errors):
    """Forma de cada item de la lista spec.list_key y rangos de cantidad y precio."""
    items = params.get(spec.list_key)
    if type(items) is not list:
        return
    for index, item in enumerate(items):
        if type(item) is not dict:
            errors.add("invalid_type", "%s[%s] (dict)" % (spec.list_key, index))
            continue
        prefix = "%s[%s]." % (spec.list_key, index)
        unknown_keys = set(item) - set(spec.schema) - spec.optional
        for param in sorted(unknown_keys):
            errors.add("unknown", prefix + param)
        item_errors = ParamErrors()
        check_schema(item, spec.schema, item_errors, prefix)
        errors.extend(item_errors)
        tipo = item.get(spec.tipo)
        if tipo is not None:                    # caso de productos retornables, requieren tipo
            if type(tipo) is not str:
                errors.add("invalid_type", prefix + spec.tipo + " (str)")
            elif tipo not in CONTAINER_STATE:
                errors.add("invalid_value", prefix + spec.tipo + " (%s)" % "/".join(CONTAINER_STATE))
        series = item.get(spec.series)
        if series is not None:                  # caso de productos con seguimiento por numero de serie, requieren series
            if type(series) is not list:
                errors.add("invalid_type", prefix + spec.series + " (list)")
            else:
                for serie_index, serie in enumerate(series):
                    if type(serie) is not str or not serie.strip():
                        errors.add("invalid_type", "%s%s[%s] (str)" % (prefix, spec.series, serie_index))
        if item_errors:
            continue
        if item[spec.qty] <= 0:
            errors.add("invalid_value", prefix + spec.qty + " (> 0)")
        if spec.price and item[spec.price] < 0:
            errors.add("invalid_value", prefix + spec.price + " (>= 0)")


def validate_tipo(items, products_by_code, spec=SALE_ITEMS):
    """tipo (venta_tipo_envase / retiro_tipo_envase): obligatorio solo en productos que requieren estado de envase.
    En la venta se acepta tambien en retornables frio/calor; en el retiro (strict_tipo) no:
    el frio/calor se identifica por serie."""
    errors = ParamErrors()
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        has_tipo = item.get(spec.tipo) is not None
        prefix = "%s[%s]." % (spec.list_key, index)
        if requires_container_state(product) and not has_tipo:
            errors.add("missing", prefix + spec.tipo + " (%s es retornable)" % product.default_code)
        elif spec.strict_tipo and not requires_container_state(product) and has_tipo:
            errors.add("not_applicable", prefix + spec.tipo + " (%s no admite tipo de envase)" % product.default_code)
        elif not spec.strict_tipo and not product.is_returnable and has_tipo:
            errors.add("not_applicable", prefix + spec.tipo + " (%s no es retornable)" % product.default_code)
    return errors


def validate_series(items, products_by_code, spec=SALE_ITEMS):
    """series: obligatoria (una por unidad) solo con seguimiento por numero de serie.
    Devuelve (errors, requested_series) con requested_series = {(product_id, serie)}."""
    errors = ParamErrors()
    requested_series = set()
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        series = item.get(spec.series) or []
        prefix = "%s[%s]." % (spec.list_key, index)
        if product.tracking != "serial":
            if series:
                errors.add("not_applicable", prefix + spec.series + " (%s no tiene seguimiento por serie)" % product.default_code)
            continue
        if not series:
            errors.add("missing", prefix + spec.series + " (%s tiene seguimiento por serie)" % product.default_code)
            continue
        if not float(item[spec.qty]).is_integer() or len(series) != item[spec.qty]:
            errors.add("invalid_value", prefix + spec.series + " (una serie por unidad: cantidad entera igual a %s series)" % len(series))
        for serie in series:
            if (product.id, serie) in requested_series:
                errors.add("invalid_value", prefix + spec.series + " (%s repetida)" % serie)
            requested_series.add((product.id, serie))
    return errors, requested_series


@dataclass(frozen=True)
class WithdrawalAvailability:
    """Envases del cliente, ya leidos de la base.
    quantity: {(product_template_id, estado): cantidad}, solo envases con cantidad > 0.
    lots: {(product_template_id, nombre_de_serie): lote} de los envases con serie."""
    quantity: dict
    lots: dict


def validate_withdrawal_availability(items, products_by_code, availability):
    """Que el cliente tenga lo que se retira. Los repetidos se suman por
    (producto, estado). Los productos con serie se validan por serie."""
    errors = ParamErrors()
    requested = {}          # {(template, estado): cantidad pedida}
    code_by_template = {}   # {template: default_code}, solo para el mensaje de error
    for index, item in enumerate(items):
        product = products_by_code[item[WITHDRAWAL_ITEMS.code]]
        tmpl_id = product.product_tmpl_id.id # availability indexada x template
        if product.tracking == "serial":
            prefix = "%s[%s]." % (WITHDRAWAL_ITEMS.list_key, index)
            for serie in item.get(WITHDRAWAL_ITEMS.series) or []:
                if (tmpl_id, serie) not in availability.lots:
                    errors.add("invalid_value", prefix + WITHDRAWAL_ITEMS.series + " (%s no es un envase del cliente)" % serie)
        if requires_container_state(product):
            state = CONTAINER_STATE[item[WITHDRAWAL_ITEMS.tipo]]
            key = (tmpl_id, state)
            requested[key] = requested.get(key, 0) + item[WITHDRAWAL_ITEMS.qty]
            code_by_template[tmpl_id] = product.default_code
    for (tmpl_id, state), quantity in requested.items():
        available = availability.quantity.get((tmpl_id, state), 0)
        if quantity > available:
            code = code_by_template[tmpl_id]
            errors.add("invalid_value", "%s (%s en estado %s: se retiran %s, el cliente tiene %s)" % (
                WITHDRAWAL_ITEMS.qty, code, state, quantity, available,
            ))
    return errors
