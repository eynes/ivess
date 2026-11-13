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

# Recambio de envases: se combina con una venta o con un motivo de no compra; nunca va solo.
REPLACEMENT_SCHEMA = {
    "item_recambio": list,
}
REPLACEMENT_REASON_SCHEMA = {
    "recambio_motivo": int,
}
REPLACEMENT_ITEM_SCHEMA = {
    "recambio_cod_producto": str,
    "recambio_cantidad": (int, float),
}
REPLACEMENT_ITEM_OPTIONAL = {"recambio_tipo_envase", "recambio_series_entregado", "recambio_series_recibido"}

CONTAINER_STATE = {
    "V": "en_comodato",
    "P": "prestado",
}


@dataclass(frozen=True)
class ItemSpec:
    """Nombres de los campos de una lista de items. Venta, retiro y recambio se
    validan con las mismas reglas; solo cambian los nombres de los campos.
    series_received: solo el recambio, que tiene dos listas de series: series
    es la del envase entregado y series_received la del recibido."""
    list_key: str
    code: str
    qty: str
    tipo: str
    series: str
    schema: dict
    optional: set
    price: str | None = None
    series_received: str | None = None
    requires_replacement: bool = False


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
)
REPLACEMENT_ITEMS = ItemSpec(
    "item_recambio",
    "recambio_cod_producto",
    "recambio_cantidad",
    "recambio_tipo_envase",
    "recambio_series_entregado",
    REPLACEMENT_ITEM_SCHEMA,
    REPLACEMENT_ITEM_OPTIONAL,
    series_received="recambio_series_recibido",
    requires_replacement=True,
)
REPLACEMENT_REASON_KEY = "recambio_motivo"

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
    """Parametros propios del caso: item_retiro, item_recambio y recambio_motivo
    siempre; item_venta solo cuando no hay motivo de no compra."""
    names = {WITHDRAWAL_ITEMS.list_key, REPLACEMENT_ITEMS.list_key, REPLACEMENT_REASON_KEY}
    if params["motivo_no_compra"] == 0:
        names.add(SALE_ITEMS.list_key)
    return names


def validate_case_params(params):
    """Fase 2: parametros propios del caso (item_venta, item_retiro, item_recambio
    y cada item). Sin motivo de no compra la visita es una venta: item_venta es
    obligatorio. item_retiro e item_recambio acompanan a una venta o a una no
    compra; nunca van solos. recambio_motivo es obligatorio con item_recambio y
    no aplica sin el."""
    errors = ParamErrors()
    if params["motivo_no_compra"] == 0:
        check_schema(params, SALE_SCHEMA, errors)
    # item_retiro en null equivale a ausente; una lista vacia es faltante.
    if params.get(WITHDRAWAL_ITEMS.list_key) is not None:
        check_schema(params, WITHDRAWAL_SCHEMA, errors)
    # Idem item_recambio; recambio_motivo se exige solo si hay recambio.
    if params.get(REPLACEMENT_ITEMS.list_key) is not None:
        check_schema(params, REPLACEMENT_SCHEMA, errors)
        check_schema(params, REPLACEMENT_REASON_SCHEMA, errors)
    elif params.get(REPLACEMENT_REASON_KEY) is not None:
        errors.add("not_applicable", REPLACEMENT_REASON_KEY + " (sin item_recambio)")
    for spec in (SALE_ITEMS, WITHDRAWAL_ITEMS, REPLACEMENT_ITEMS):
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
        # caso de productos con seguimiento por numero de serie, requieren series
        # (el recambio tiene dos listas: entregado y recibido)
        for series_key in (spec.series, spec.series_received):
            series = item.get(series_key) if series_key else None
            if series is None:
                continue
            if type(series) is not list:
                errors.add("invalid_type", prefix + series_key + " (list)")
            else:
                for serie_index, serie in enumerate(series):
                    if type(serie) is not str or not serie.strip():
                        errors.add("invalid_type", "%s%s[%s] (str)" % (prefix, series_key, serie_index))
        if item_errors:
            continue
        if item[spec.qty] <= 0:
            errors.add("invalid_value", prefix + spec.qty + " (> 0)")
        if spec.price and item[spec.price] < 0:
            errors.add("invalid_value", prefix + spec.price + " (>= 0)")


def validate_tipo(items, products_by_code, spec=SALE_ITEMS):
    """tipo (venta_tipo_envase / retiro_tipo_envase / recambio_tipo_envase): obligatorio solo en productos que requieren estado de envase.
    En cualquier otro producto es not_applicable: el frio/calor queda siempre en estado asignado."""
    errors = ParamErrors()
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        has_tipo = item.get(spec.tipo) is not None
        prefix = "%s[%s]." % (spec.list_key, index)
        if requires_container_state(product) and not has_tipo:
            errors.add("missing", prefix + spec.tipo + " (%s es retornable)" % product.default_code)
        elif not requires_container_state(product) and has_tipo:
            errors.add("not_applicable", prefix + spec.tipo + " (%s no admite tipo de envase)" % product.default_code)
    return errors


def validate_is_container(items, products_by_code, spec):
    """El producto de retiro o recambio tiene que ser un envase (retornable o
    frio/calor). Sin esto, un producto comun pasaba la validacion y recien
    fallaba (o no) contra los envases del cliente."""
    errors = ParamErrors()
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        if not (product.is_returnable or product.is_frio_calor):
            prefix = "%s[%s]." % (spec.list_key, index)
            errors.add("invalid_value", prefix + spec.code + " (%s no es un envase)" % product.default_code)
    return errors


def validate_allows_replacement(items, products_by_code, spec):
    """Solo los productos con allows_replacement admiten recambio. Aplica solo a
    los specs que lo exigen (requires_replacement): el retiro no tiene esta
    restriccion, asi que con su spec no devuelve errores."""
    errors = ParamErrors()
    if not spec.requires_replacement:
        return errors
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        if not product.allows_replacement:
            prefix = "%s[%s]." % (spec.list_key, index)
            errors.add("invalid_value", prefix + spec.code + " (%s no admite recambio)" % product.default_code)
    return errors


def validate_series(items, products_by_code, spec=SALE_ITEMS, series_key=None):
    """series: obligatoria (una por unidad) solo con seguimiento por numero de serie.
    series_key es la lista a validar; por defecto spec.series. El recambio tiene
    dos: spec.series (envase entregado) y spec.series_received (recibido).
    Devuelve (errors, requested_series) con requested_series = {(product_id, serie)}."""
    series_key = series_key or spec.series
    errors = ParamErrors()
    requested_series = set()
    for index, item in enumerate(items):
        product = products_by_code[item[spec.code]]
        series = item.get(series_key) or []
        prefix = "%s[%s]." % (spec.list_key, index)
        if product.tracking != "serial":
            if series:
                errors.add("not_applicable", prefix + series_key + " (%s no tiene seguimiento por serie)" % product.default_code)
            continue
        if not series:
            errors.add("missing", prefix + series_key + " (%s tiene seguimiento por serie)" % product.default_code)
            continue
        if len(series) != item[spec.qty]:
            errors.add("invalid_value", prefix + series_key + " (una serie por unidad: cantidad entera igual a %s series)" % len(series))
        for serie in series:
            if (product.id, serie) in requested_series:
                errors.add("invalid_value", prefix + series_key + " (%s repetida)" % serie)
            requested_series.add((product.id, serie))
    return errors, requested_series


def validate_series_overlap(first, second, first_name, second_name):
    """Una misma serie no puede estar en dos lados de la request a la vez:
    entregado y recibido del recambio, venta y entregado, retiro y recibido.
    first y second son sets {(product_id, serie)}; first_name y second_name
    nombran la lista de cada uno, solo para el mensaje."""
    errors = ParamErrors()
    for _product_id, serie in sorted(first & second): #interseccion de conjuntos (series repetidas)
        errors.add("invalid_value", "%s (%s esta en %s y en %s)" % (first_name, serie, first_name, second_name))
    return errors


FRIO_CALOR_STATE = "asignado"


def effective_state(product, tipo):
    """Estado de envase con el que el producto queda (o esta) en el cliente:
    el que indica tipo en retornables comunes, 'asignado' en frio/calor (el
    tipo no se informa) y None si el producto no es envase."""
    if requires_container_state(product):
        return CONTAINER_STATE[tipo]
    if product.is_frio_calor:
        return FRIO_CALOR_STATE
    return None


@dataclass(frozen=True)
class CustomerContainers:
    """Envases del cliente, ya leidos de la base. Todo indexado por
    product_template_id (water.container.product_id es un template).
    quantity: {(template, estado): cantidad}, solo envases con cantidad > 0.
    lots: {(template, nombre_de_serie): lote} de los envases con serie.
    lot_states: {(template, nombre_de_serie): estado} de esos mismos envases."""
    quantity: dict
    lots: dict
    lot_states: dict


def validate_customer_availability(demands, products_by_code, containers):
    """Que el cliente tenga lo que se le saca: retiro y lado recibido del recambio.
    demands: lista de (spec, series_key, items), un elemento por flujo. La
    demanda se suma entre flujos, porque salen del mismo stock del cliente.
    Con serie, se valida cada serie: que sea un envase del cliente y que este
    en el estado efectivo del item. Sin serie, las cantidades se suman por
    (template, estado efectivo), tambien en frio/calor ('asignado')."""
    errors = ParamErrors()
    requested = {}          # {(template, estado): cantidad pedida}
    sources = {}            # {(template, estado): {campos de cantidad}}, solo para el mensaje
    code_by_template = {}   # {template: default_code}, solo para el mensaje
    for spec, series_key, items in demands:
        for index, item in enumerate(items):
            product = products_by_code[item[spec.code]]
            tmpl_id = product.product_tmpl_id.id    # containers indexado x template
            state = effective_state(product, item.get(spec.tipo))
            if state is None:                       # no es envase: lo rechaza validate_is_container
                continue
            if product.tracking == "serial":
                prefix = "%s[%s]." % (spec.list_key, index)
                for serie in item.get(series_key) or []:
                    key = (tmpl_id, serie)
                    if key not in containers.lots:
                        errors.add("invalid_value", prefix + series_key + " (%s no es un envase del cliente)" % serie)
                    elif containers.lot_states[key] != state:
                        errors.add("invalid_value", prefix + series_key + " (%s esta en estado %s y se informo %s)" % (
                            serie, containers.lot_states[key], state,
                        ))
                continue
            key = (tmpl_id, state)
            requested[key] = requested.get(key, 0) + item[spec.qty]
            sources.setdefault(key, set()).add(spec.qty)
            code_by_template[tmpl_id] = product.default_code
    for (tmpl_id, state), quantity in requested.items():
        available = containers.quantity.get((tmpl_id, state), 0)
        if quantity > available:
            errors.add("invalid_value", "%s (%s en estado %s: se sacan %s, el cliente tiene %s)" % (
                " + ".join(sorted(sources[(tmpl_id, state)])), code_by_template[tmpl_id], state, quantity, available,
            ))
    return errors
