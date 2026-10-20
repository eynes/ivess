{
    'name': "Ivess Public Holiday Workday",
    'version': '19.0.1.0.0',
    'summary': "Feriados laborables sobre calendar_public_holiday",
    'description': """
        Agrega a las líneas de feriados (calendar.public.holiday.line) el campo
        "Laborable". Un feriado marcado como laborable queda registrado en el
        calendario (evento) pero no se excluye como día no laborable en
        Time Off / días inusuales.
    """,
    'author': "Eynes",
    'category': 'Human Resources',
    'depends': [
        'calendar_public_holiday',
        'hr_holidays_public',
    ],
    'data': [
        'data/calendar_event_type_data.xml',
        'views/calendar_public_holiday_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
