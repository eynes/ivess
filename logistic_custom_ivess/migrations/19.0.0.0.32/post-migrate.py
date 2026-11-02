def migrate(cr, version):
    """T17813: renumera el orden de cada plantilla (1, 2, 3...).

    Hasta ahora las líneas de plantilla nacían todas con orden 10, así que
    había órdenes repetidos. Se conserva el orden actual y se desempata por id.
    Los recorridos ya generados no se tocan."""
    cr.execute("""
        WITH renumbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY template_route_id ORDER BY sequence, id
                   ) AS new_sequence
              FROM delivery_route_line
             WHERE template_route_id IS NOT NULL
               AND route_id IS NULL
        )
        UPDATE delivery_route_line drl
           SET sequence = renumbered.new_sequence,
               template_order = renumbered.new_sequence
          FROM renumbered
         WHERE renumbered.id = drl.id
           AND drl.sequence IS DISTINCT FROM renumbered.new_sequence
    """)
    # partner.distribution.orden es related almacenado de la línea de plantilla.
    cr.execute("""
        UPDATE partner_distribution pd
           SET orden = drl.sequence
          FROM delivery_route_line drl
         WHERE drl.id = pd.route_line_id
           AND pd.orden IS DISTINCT FROM drl.sequence
    """)
