"""
Carga masiva de números de serie en Odoo.sh via XML-RPC.
Corre localmente — no requiere acceso SSH ni subir archivos al servidor.

Columnas del CSV:
    ref, Idproducto, Nro_Serie, Marca, Modelo, Fecha_Alta, Fecha_Modificacion

Mapeo a stock.lot:
    Nro_Serie  → name
    ref        → ref
    Marca      → brand
    Modelo     → model
    Fecha_Alta → registration_date

Uso:
    python3 load_serial_numbers_xmlrpc.py
"""

import csv
import xmlrpc.client
import sys
from datetime import datetime

# ── Configuración ────────────────────────────────────────────────────────────
ODOO_URL     = "https://stage.odoo.com"   # Sin barra final ej. "https://instancia.odoo.com"
ODOO_DB      = "db_name"                  # Nombre de la DB en Odoo.sh
ODOO_USER    = "admin"        # Email del usuario
ODOO_API_KEY = "API_KEY"      # Configuración > Usuarios > Seguridad > Nueva clave API

CSV_PATH     = "/rut/serial.csv"    # Ruta al CSV en tu máquina
PRODUCT_ID   = 8558                 # product.product id de "Equipo Frio Calor"
BATCH_SIZE   = 200                  # Registros por llamada
# ─────────────────────────────────────────────────────────────────────────────

# Formatos de fecha que puede traer el CSV (se prueban en orden)
DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"]

def parse_date(value):
    """Devuelve string 'YYYY-MM-DD' o None si el valor está vacío o no parsea."""
    if not value or not value.strip():
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    print(f"  ADVERTENCIA: no se pudo parsear la fecha '{value}', se ignorará.", file=sys.stderr)
    return None

def connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_API_KEY, {})
    if not uid:
        print("ERROR: Autenticación fallida. Verificá URL, DB, usuario y API key.")
        sys.exit(1)
    print(f"Conectado como UID {uid}")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models

def call(models, uid, model, method, *args, **kwargs):
    return models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, model, method, list(args), kwargs)

def build_vals(row, company_id):
    """Construye el dict de valores para un registro a partir de una fila del CSV."""
    vals = {
        "product_id": PRODUCT_ID,
        "company_id": company_id,
        "name":  row["Nro_Serie"].strip(),
    }
    if row.get("ref", "").strip():
        vals["ref"] = row["ref"].strip()
    if row.get("Marca", "").strip():
        vals["brand"] = row["Marca"].strip()
    if row.get("Modelo", "").strip():
        vals["model"] = row["Modelo"].strip()
    date = parse_date(row.get("Fecha_Alta", ""))
    if date:
        vals["registration_date"] = date
    return vals

def main():
    uid, models = connect()

    # Leer CSV completo
    print(f"Leyendo {CSV_PATH}...")
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Nro_Serie", "").strip()]

    print(f"Total en CSV: {len(rows)}")

    # Detectar duplicados (buscar de a 1000 para no saturar el request)
    all_names = [r["Nro_Serie"].strip() for r in rows]
    print("Verificando duplicados existentes en Odoo...")
    existing = set()
    check_batch = 1000
    for i in range(0, len(all_names), check_batch):
        chunk = all_names[i : i + check_batch]
        found = call(
            models, uid, "stock.lot", "search_read",
            [("product_id", "=", PRODUCT_ID), ("name", "in", chunk)],
            fields=["name"], limit=check_batch,
        )
        existing.update(r["name"] for r in found)

    to_create = [r for r in rows if r["Nro_Serie"].strip() not in existing]
    print(f"Ya existentes: {len(existing)} | A crear: {len(to_create)}")

    if not to_create:
        print("Nada que crear.")
        return

    # Obtener company_id
    company_id = call(models, uid, "res.users", "read", [uid], fields=["company_id"])[0]["company_id"][0]

    # Crear en lotes
    created = 0
    errors = 0
    total = len(to_create)

    for i in range(0, total, BATCH_SIZE):
        batch = to_create[i : i + BATCH_SIZE]
        vals_list = [build_vals(row, company_id) for row in batch]
        try:
            call(models, uid, "stock.lot", "create", vals_list)
            created += len(batch)
            pct = created * 100 // total
            print(f"  [{pct:3d}%] {created}/{total} creados...", end="\r")
        except Exception as e:
            errors += len(batch)
            print(f"\n  ERROR en lote {i}-{i+len(batch)}: {e}", file=sys.stderr)

    print(f"\n\nFinalizado. Creados: {created} | Errores: {errors}")

if __name__ == "__main__":
    main()
