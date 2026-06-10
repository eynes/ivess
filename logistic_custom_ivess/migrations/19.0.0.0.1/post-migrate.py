def migrate(cr, version):
    # Migrate existing Many2one data into the new Many2many relation table
    cr.execute("""
        INSERT INTO delivery_route_number_ir_sequence_rel (route_number_id, sequence_id)
        SELECT id, remittance_sequence_id
        FROM delivery_route_number
        WHERE remittance_sequence_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    # Drop the now-orphaned Many2one column
    cr.execute("""
        ALTER TABLE delivery_route_number
        DROP COLUMN IF EXISTS remittance_sequence_id
    """)
