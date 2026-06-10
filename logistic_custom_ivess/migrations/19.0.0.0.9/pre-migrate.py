def migrate(cr, version):
    # assignment_date pasa a ser campo computado: quitar la restricción NOT NULL
    cr.execute("""
        ALTER TABLE water_container
        ALTER COLUMN assignment_date DROP NOT NULL
    """)
