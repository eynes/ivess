{
    "name": "Ivess Journal Sequence Sudo",
    "version": "19.0.1.0.0",
    "summary": "Permite crear diarios a usuarios sin rol Administrador (secuencias con sudo)",
    "description": """
        Al crear un diario de venta/cobro/pago/retenciones/percepciones,
        l10n_ar_eynes crea las secuencias del diario (ir.sequence) sin sudo.
        ir.sequence solo permite crear a base.group_system, por lo que un
        usuario con rol "Usuario" recibe "Error de acceso: No puede crear
        registros 'Secuencia' (ir.sequence)" (p. ej. al crear un Diario
        Operativo a Resumir desde el asistente de cierre mensual).

        Este módulo sobreescribe create_pos_sequence para crear las secuencias
        con sudo, sin ampliar los permisos de ir.sequence.

        NOTA: este fix conviene incorporarlo directamente en l10n_ar_eynes
        (account.journal.create_pos_sequence), de modo que beneficie a otros
        clientes y futuros cambios. Cuando eso ocurra, este módulo se puede
        desinstalar y eliminar.
    """,
    "author": "Eynes",
    "category": "Accounting",
    "depends": [
        "l10n_ar_eynes",
    ],
    "data": [],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
