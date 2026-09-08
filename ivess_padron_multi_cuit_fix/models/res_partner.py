import json
import logging
from datetime import date

import requests

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.l10n_ar_padron_ws_consumer.models.res_partner import HEADERS
from odoo.addons.l10n_ar_padron_ws_consumer.utils.helpers import get_current_period

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Full copy-override of l10n_ar_padron_ws_consumer's do_update_from_padron.
    # Upstream resolves the partner to update with a bare search on `vat`
    # (limit=1, no `id` restriction), so when two res.partner share a CUIT
    # the update lands on whichever one Odoo's default order returns first,
    # not on the partner(s) that actually requested it. We can't touch that
    # method inside l10n_ar_eynes (shared repo, other clients depend on it),
    # so we duplicate it here and resolve partners from the already-scoped
    # `partners` recordset instead of re-searching the whole table.
    def do_update_from_padron(  # noqa: C901
        self,
        padron_name=None,
        padron_type=None,
        from_cron=None,
        only_from_today=False,
        use_special_padron=None,
        check_server_state=False,
    ):
        if padron_name is None:
            padron_name = []

        if padron_type is None:
            padron_type = []
        if use_special_padron is None:
            use_special_padron = self.env.company.use_special_padron

        padron_url = self._get_padron_url()
        payload = {
            "status": True,
        }

        check_padron_server_state = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('l10n_ar_padron_ws_consumer.check_padron_server_state')
        )

        if check_server_state or check_padron_server_state:
            try:
                _logger.info('Checking Padron URL State')
                response = requests.head(
                    padron_url,
                    headers=HEADERS,
                    data=json.dumps(payload),
                    timeout=60,
                )
                if response.status_code != 200:
                    raise ValidationError(
                        _("Padron Error!\n") + _("Error in response CODE.")
                    )
            except requests.RequestException as err:
                raise ValidationError(
                    _("Padron Error!\n") + _("Padron server is not reachable.")
                ) from err

        self._cleanup_old_padron_values()

        _logger.info('Update Padron')

        valid_document_types = [
            self.env.ref("l10n_ar_eynes.document_cuit").id,
            self.env.ref("l10n_ar_eynes.document_cuit_country").id,
        ]
        padron_url = self._get_padron_url()
        current_period = get_current_period()
        domain = [
            ('document_type_id', 'in', valid_document_types),
            ('parent_id', '=', False),
            ('vat', '!=', False),
        ]
        if only_from_today:
            today = date.today()
            domain.append(('create_date', '>=', today))
        partner_ids = self.env.context.get('active_ids', [])
        if partner_ids:
            domain_append = [('id', 'in', partner_ids)]
        else:
            domain_append = [
                '|',
                ('last_padron_update', '=', False),
                ('last_padron_update', '<', current_period),
            ]
        domain = domain + domain_append
        res_partner_obj = self.env["res.partner"]
        partners = res_partner_obj.search(domain)
        _logger.info('Getting Padron Information')
        if partners:
            valid_vat = self._validate_partners_vat(partners, from_cron)

            updates = set()
            response = self._get_padron_values(
                valid_vat, padron_url, padron_name, padron_type, from_cron
            )
            _logger.info('Padron Information Fetched')
            for vat, partner_values in response.items():
                try:
                    perceptions = False
                    retentions = False
                    if use_special_padron:
                        perceptions = [
                            d
                            for d in partner_values
                            if d["P"] == "SPECIAL" and d["T"] == "P"
                        ]
                        retentions = [
                            d
                            for d in partner_values
                            if d["P"] == "SPECIAL" and d["T"] == "R"
                        ]
                    if not perceptions:
                        perceptions = [
                            d
                            for d in partner_values
                            if d["T"] == "P" and d["P"] != "SALT"
                        ]
                    if not retentions:
                        retentions = [
                            d for d in partner_values if d["T"] == "R"
                        ]
                    coeficients = [
                        d
                        for d in partner_values
                        if d["T"] == "C" or (d["T"] == "P" and d["P"] == "SALT")
                    ]
                    ivas = [d for d in partner_values if d["T"] == "I"]

                    # Fix: update every partner in this batch that carries
                    # this vat, instead of re-searching the whole table by
                    # vat alone (which could return an unrelated partner
                    # when the CUIT is shared by more than one res.partner).
                    matching_partners = partners.filtered(
                        lambda p, vat=vat: p.vat == vat
                    )
                    for partner_id in matching_partners:
                        self._update_partner_perceptions(partner_id, perceptions)
                        self._update_partner_retentions(partner_id, retentions)
                        self._update_partner_coeficients(partner_id, coeficients)
                        self._update_partner_ivas(partner_id, ivas)
                        partner_id.write(
                            {
                                "last_padron_update": current_period,
                            }
                        )
                    total_updates = perceptions + retentions + coeficients
                    new_values = {
                        value
                        for value in [
                            value["P"] + " - " + value["M"]
                            for value in total_updates
                        ]
                    }
                    updates.update(new_values)
                except Exception:
                    _logger.exception(
                        "Error updating partner from padron for VAT %s", vat
                    )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'sticky': True,
                    'message': (
                        "Se actualizaron los siguientes Padrones: "
                        + " | ".join([value for value in updates])
                    ),
                },
            }

    # Full copy-override of l10n_ar_padron_ws_consumer's
    # _get_journal_from_padron_name. Upstream's domain has no company_id
    # filter, so in a multi-company database it returns one journal per
    # company sharing the same perception/retention code. It also only
    # recognizes "SALT" for Salta, while real Padron responses also send
    # "SALTD" for the same jurisdiction (seen live for CUIT 30500000127 and
    # 30500683267) -- an unrecognized name skips the padron_state_id filter
    # entirely, matching every province's journal at once. Either gap makes
    # `_update_partner_perceptions`/`_update_partner_retentions` crash with
    # "Expected singleton" on `journal_id.tax_id.id`.
    def _get_journal_from_padron_name(self, padron_name, padron_type):
        domain = [
            ("type", "=", padron_type),
            ("company_id", "=", self.env.company.id),
        ]
        if padron_name == "IVA":
            domain.append(("code", '=', 'PIVAE'))
        else:
            if padron_name == "ARBA":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_b').id)
                )
            elif padron_name in ("CABA", "SPECIAL"):
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_c').id)
                )
            elif padron_name == "CORD":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_x').id)
                )
            elif padron_name == "JUJU":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_y').id)
                )
            elif padron_name == "TUCU":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_t').id)
                )
            elif padron_name == "MEND":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_m').id)
                )
            elif padron_name in ("SALT", "SALTD"):
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_a').id)
                )
            elif padron_name == "FORM":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_p').id)
                )
            elif padron_name == "SANT":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_s').id)
                )
            elif padron_name == "ENTR":
                domain.append(
                    ("padron_state_id", '=', self.env.ref('base.state_ar_e').id)
                )

            if padron_type == 'perceptions':
                domain.append(("code", 'like', 'PIE_'))
            elif padron_type == 'retentions':
                domain.append(("code", 'like', 'RIE_'))

        return self.env["account.journal"].search(domain)
