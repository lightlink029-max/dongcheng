from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    psc_local_worker_token = fields.Char(
        string="工作节点令牌", config_parameter="psc.local_worker_token",
    )
    psc_local_worker_lease_seconds = fields.Integer(
        string="任务租约（秒）", default=900,
        config_parameter="psc.local_worker_lease_seconds",
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        values["psc_local_worker_token"] = self.env[
            "psc.local.production.task"
        ].get_or_create_worker_token()
        return values

    @api.constrains("psc_local_worker_lease_seconds")
    def _check_local_worker_lease(self):
        for settings in self:
            if not 60 <= settings.psc_local_worker_lease_seconds <= 3600:
                raise ValidationError("本地任务租约必须在 60 到 3600 秒之间。")
