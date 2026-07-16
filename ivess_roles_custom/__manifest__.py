# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "IVESS - Roles y Permisos Compras y Abastecimiento",
    "version": "19.0.1.0.0",
    "summary": "Matriz de permisos para los roles del área de Compras y Abastecimiento",
    "description": """
        Implementa la matriz de accesos para los roles del área de Compras
        y Abastecimiento usando los grupos nativos de Odoo:

        Compras:
          · Usuario Compras       (purchase.group_purchase_user)
          · Administrador Compras (purchase.group_purchase_manager)

        Inventario:
          · Usuario Inventario        (stock.group_stock_user)
          · Administrador Inventario  (stock.group_stock_manager)

        Solicitudes de Existencias:
          · Usuario Solicitudes (stock_request.group_stock_request_user)

        Administración:
          · Usuario Administración  (ivess_roles_custom.group_admin_user)
          · Administrador Admin.    (base.group_system)

        Control total:
          · Administrador TOTAL (base.group_system)

        La matriz de permisos completa está documentada en
        security/ir.model.access.csv y en los comentarios de security/security.xml.
    """,
    "category": "Inventory",
    "author": "Eynes",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "stock",
        "account",
        "purchase_stock",
        "stock_request",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/purchase_views.xml",
        "views/stock_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
