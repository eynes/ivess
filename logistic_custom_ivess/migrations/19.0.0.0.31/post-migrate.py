# (columna Many2one vieja, tabla relacional nueva, columna de la relación)
BOOKLET_FIELDS = [
    ('remittance_sequence_id', 'delivery_route_number_remittance_seq_rel', 'sequence_id'),
    ('collection_journal_id', 'delivery_route_number_collection_journal_rel', 'journal_id'),
    ('repair_order_sequence_id', 'delivery_route_number_repair_seq_rel', 'sequence_id'),
]


def migrate(cr, version):
    for old_column, rel_table, rel_column in BOOKLET_FIELDS:
        cr.execute("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'delivery_route_number'
            AND column_name = %s
        """, (old_column,))
        if not cr.fetchone():
            continue
        # Copy existing Many2one values into the new Many2many relation table
        cr.execute(f"""
            INSERT INTO {rel_table} (route_number_id, {rel_column})
            SELECT id, {old_column}
            FROM delivery_route_number
            WHERE {old_column} IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        # CASCADE: ivess_delivery_and_assigned_route_report (ivess_webservice)
        # depends on repair_order_sequence_id; its init() recreates the view
        cr.execute(f"""
            ALTER TABLE delivery_route_number
            DROP COLUMN IF EXISTS {old_column} CASCADE
        """)
