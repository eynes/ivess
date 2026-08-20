###############################################################################
#
#    Copyright (c) 2026 Eynes/E-MIPS (www.eynes.com.ar)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
# pylint: disable=manifest-required-author, missing-readme

{
    'name': 'Internal Voucher',
    'version': '19.0.1.0.0',
    'author': 'Eynes',
    'website': 'https://gitlab.eynes.com.ar/localization/l10n_ar_eynes/',
    'license': 'AGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'l10n_ar_eynes',
    ],
    'data': [
        'views/account_journal_views.xml',
    ],
    'installable': True,
    'application': False,
}
