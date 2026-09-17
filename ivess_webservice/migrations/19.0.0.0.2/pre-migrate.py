def migrate(cr, version):
    cr.execute("""
        DROP TABLE IF EXISTS ivess_customer_category_report CASCADE;
    """)
