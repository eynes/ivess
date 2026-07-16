def migrate(cr, version):
    # Drop dependent SQL views before altering columns
    cr.execute("DROP VIEW IF EXISTS ivess_container_loan_report")

    # Populate new 'state' selection from the old Many2one
    cr.execute("""
        UPDATE water_container wc
        SET state = CASE
                WHEN LOWER(wcs.name) LIKE '%comodato%' THEN 'en_comodato'
                ELSE 'prestado'
            END
        FROM water_container_state wcs
        WHERE wc.state_id = wcs.id
    """)
    cr.execute("ALTER TABLE water_container DROP COLUMN IF EXISTS state_id")

    # Populate new 'container_state' selection in stock_move from the old Many2one
    cr.execute("""
        UPDATE stock_move sm
        SET container_state = CASE
            WHEN LOWER(wcs.name) LIKE '%comodato%' THEN 'en_comodato'
            ELSE 'prestado'
        END
        FROM water_container_state wcs
        WHERE sm.container_state_id = wcs.id
    """)
    cr.execute("ALTER TABLE stock_move DROP COLUMN IF EXISTS container_state_id")

    # Drop the now-obsolete model table
    cr.execute("DROP TABLE IF EXISTS water_container_state")
