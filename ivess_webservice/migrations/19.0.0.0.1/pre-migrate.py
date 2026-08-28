def migrate(cr, version):
    cr.execute("""
        DROP VIEW IF EXISTS ivess_customer_category CASCADE;
        DROP VIEW IF EXISTS ivess_fiscal_position_report CASCADE;
        DROP VIEW IF EXISTS ivess_limit_free_of_charge_report CASCADE;
        DROP VIEW IF EXISTS ivess_localities_report CASCADE;
        DROP VIEW IF EXISTS ivess_no_purchase_reason_report CASCADE;
        DROP VIEW IF EXISTS ivess_replacement_reason_report CASCADE;
        DROP VIEW IF EXISTS ivess_talonarios_report CASCADE;
    """)
