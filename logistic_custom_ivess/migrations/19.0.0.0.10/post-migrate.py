def migrate(cr, version):
    # Migrate visit_hour (single float) to visit_hour_from / visit_hour_to range fields.
    # visit_hour_to = visit_hour_from + 3h, capped at 19.0; values outside 7-19 are left as 0.
    cr.execute("""
        UPDATE res_partner
        SET visit_hour_from = visit_hour,
            visit_hour_to = CASE
                WHEN visit_hour >= 7.0 AND visit_hour + 3.0 <= 19.0 THEN visit_hour + 3.0
                WHEN visit_hour >= 7.0 AND visit_hour + 3.0 > 19.0  THEN 19.0
                ELSE 0.0
            END
        WHERE visit_hour IS NOT NULL AND visit_hour > 0
    """)
    cr.execute("""
        UPDATE delivery_route_line
        SET visit_hour_from = visit_hour,
            visit_hour_to = CASE
                WHEN visit_hour >= 7.0 AND visit_hour + 3.0 <= 19.0 THEN visit_hour + 3.0
                WHEN visit_hour >= 7.0 AND visit_hour + 3.0 > 19.0  THEN 19.0
                ELSE 0.0
            END
        WHERE visit_hour IS NOT NULL AND visit_hour > 0
    """)
