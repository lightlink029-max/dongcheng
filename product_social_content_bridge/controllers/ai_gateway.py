import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


class LightLinkAiGateway(http.Controller):
    """Small business API consumed by the LightLink ChatGPT MCP server."""

    def _payload(self):
        payload = request.httprequest.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValidationError("请求正文必须是 JSON 对象。")
        return payload

    def _call(self, method_name):
        try:
            payload = self._payload()
            result = getattr(request.env["psc.ai.service"], method_name)(**payload)
            return request.make_json_response({"ok": True, "data": result})
        except AccessError as error:
            return request.make_json_response(
                {"ok": False, "error": "access_denied", "message": str(error)}, status=403,
            )
        except (UserError, ValidationError, TypeError) as error:
            return request.make_json_response(
                {"ok": False, "error": "invalid_request", "message": str(error)}, status=400,
            )
        except Exception:
            _logger.exception("LightLink AI gateway request failed: %s", method_name)
            return request.make_json_response({
                "ok": False,
                "error": "internal_error",
                "message": "Odoo处理请求失败，请在Odoo日志中查看关联错误。",
            }, status=500)

    @http.route(
        "/psc/ai/v1/projects", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def projects(self, **kwargs):
        return self._call("list_projects")

    @http.route(
        "/psc/ai/v1/runs/start", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False,
    )
    def start_run(self, **kwargs):
        return self._call("start_ai_run")

    @http.route(
        "/psc/ai/v1/runs/finish", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False,
    )
    def finish_run(self, **kwargs):
        return self._call("finish_ai_run")

    @http.route(
        "/psc/ai/v1/daily-snapshot", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def daily_snapshot(self, **kwargs):
        return self._call("get_daily_operations_snapshot")

    @http.route(
        "/psc/ai/v1/product-context", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def product_context(self, **kwargs):
        return self._call("get_product_market_context")

    @http.route(
        "/psc/ai/v1/content-backlog", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def content_backlog(self, **kwargs):
        return self._call("get_content_backlog")

    @http.route(
        "/psc/ai/v1/publication-exceptions", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def publication_exceptions(self, **kwargs):
        return self._call("get_publication_exceptions")

    @http.route(
        "/psc/ai/v1/account-health", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def account_health(self, **kwargs):
        return self._call("get_account_environment_health")

    @http.route(
        "/psc/ai/v1/priority-leads", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def priority_leads(self, **kwargs):
        return self._call("get_priority_leads")

    @http.route(
        "/psc/ai/v1/campaign-performance", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def campaign_performance(self, **kwargs):
        return self._call("get_campaign_performance")

    @http.route(
        "/psc/ai/v1/actions/prepare", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False,
    )
    def prepare_action(self, **kwargs):
        return self._call("prepare_action")

    @http.route(
        "/psc/ai/v1/actions/commit", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False,
    )
    def commit_action(self, **kwargs):
        return self._call("commit_action")

    @http.route(
        "/psc/ai/v1/actions/status", type="http", auth="bearer", methods=["POST"],
        csrf=False, save_session=False, readonly=True,
    )
    def action_status(self, **kwargs):
        return self._call("get_action_execution_status")
