# Copyright 2026 Eynes
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        if request.session.uid and info.get("user_companies"):
            user = self.env["res.users"].browse(request.session.uid)
            switcher = user._get_company_switcher_info()
            info.update(switcher)
            locked = switcher["company_locked_ids"]
            if locked:
                # No se recorta `allowed_companies`: otros módulos (hr_timesheet,
                # etc.) lo indexan por cada empresa del usuario. El alcance lo
                # fuerzan `company_locked_ids` (cliente) y el servidor.
                info["user_companies"]["current_company"] = locked[0]
        return info
