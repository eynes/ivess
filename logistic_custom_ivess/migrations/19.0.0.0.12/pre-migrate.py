def migrate(cr, version):
    cr.execute("""
        ALTER TABLE res_partner
            ADD COLUMN IF NOT EXISTS is_important_client boolean DEFAULT false,
            ADD COLUMN IF NOT EXISTS mobile_number       varchar,
            ADD COLUMN IF NOT EXISTS address_details     text
    """)
