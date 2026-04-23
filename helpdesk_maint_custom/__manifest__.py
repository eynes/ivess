# Copyright 2024 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "Custom Helpdesk Maintenance",
    "version": "19.0.1.0.0",
    "summary": "Extends Helpdesk with team types and maintenance ticket fields",
    "author": "Eynes",
    "category": "Helpdesk",
    "license": "LGPL-3",
    "depends": [
        "helpdesk",
        "hr",
        "website_helpdesk",
    ],
    "data": [
        "views/helpdesk_ticket_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    
}
