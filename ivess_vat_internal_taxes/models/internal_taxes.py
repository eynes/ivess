def get_internal_taxes(wizard, move_types, type_tax_use, sign):
    """Impuestos internos del período de un wizard de IVA (venta o compra).

    Usa el mismo criterio de comprobantes que _get_sale_data y
    _get_purchase_data de l10n_ar_eynes: publicados, del tipo pedido, con
    fecha contable dentro del rango, de la compañía y con posición fiscal.
    Suma las líneas de impuestos del grupo de tipo "internals".

    :param move_types: (facturas, notas de crédito), por ejemplo
        ('out_invoice', 'out_refund')
    :param type_tax_use: 'sale' o 'purchase'
    :param sign: 1 o -1, para que lleve el signo del resto del reporte
        (venta: -1, porque el importe del impuesto es un crédito; compra: 1)
    :return: (importe de facturas, importe de notas de crédito)
    """
    wizard.ensure_one()
    wizard.env.cr.execute(
        """
        SELECT am.move_type, COALESCE(SUM(%(sign)s * aml.balance), 0.0)
          FROM account_move_line aml
          JOIN account_move am ON am.id = aml.move_id
          JOIN account_fiscal_position afp ON afp.id = am.fiscal_position_id
          JOIN account_tax tax ON tax.id = aml.tax_line_id
          JOIN account_tax_group tg ON tg.id = tax.tax_group_id
         WHERE am.state = 'posted'
           AND am.move_type IN %(move_types)s
           AND am.date >= %(date_start)s
           AND am.date <= %(date_end)s
           AND am.company_id = %(company)s
           AND tax.type_tax_use = %(type_tax_use)s
           AND tg.group_type = 'internals'
         GROUP BY am.move_type
        """,
        {
            'sign': sign,
            'move_types': tuple(move_types),
            'date_start': wizard.date_start,
            'date_end': wizard.date_end,
            'company': wizard.company_id.id,
            'type_tax_use': type_tax_use,
        },
    )
    by_type = dict(wizard.env.cr.fetchall())
    invoice_type, refund_type = move_types
    return by_type.get(invoice_type, 0.0), by_type.get(refund_type, 0.0)
