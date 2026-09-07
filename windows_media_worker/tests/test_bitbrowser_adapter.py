import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bitbrowser_adapter import BitBrowserClient


class BitBrowserAdapterTests(unittest.TestCase):
    def response(self, payload):
        response = mock.Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    def test_rejects_non_local_api_address(self):
        with self.assertRaisesRegex(ValueError, "必须是本机"):
            BitBrowserClient("https://example.com")

    @mock.patch("bitbrowser_adapter.requests.post")
    def test_health_uses_official_endpoint_and_optional_token(self, post):
        post.return_value = self.response({"success": True})
        BitBrowserClient("http://127.0.0.1:54345/", "secret").health()
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:54345/health")
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "secret")

    @mock.patch("bitbrowser_adapter.requests.post")
    def test_lists_browsers_from_data_list(self, post):
        post.return_value = self.response({
            "success": True, "data": {"list": [{"id": "browser-1"}], "totalNum": 1},
        })
        result = BitBrowserClient("http://localhost:54345").list_browsers()
        self.assertEqual(result, [{"id": "browser-1"}])
        self.assertEqual(post.call_args.kwargs["json"], {"page": 0, "pageSize": 100})

    @mock.patch("bitbrowser_adapter.requests.post")
    def test_open_and_close_use_selected_id(self, post):
        post.return_value = self.response({"success": True, "data": {}})
        client = BitBrowserClient("http://127.0.0.1:54345")
        client.open_browser("browser-1")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:54345/browser/open")
        self.assertEqual(post.call_args.kwargs["json"]["id"], "browser-1")
        client.close_browser("browser-1")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:54345/browser/close")

    @mock.patch("bitbrowser_adapter.requests.post")
    def test_business_failure_reports_message(self, post):
        post.return_value = self.response({"success": False, "msg": "not logged in"})
        with self.assertRaisesRegex(RuntimeError, "not logged in"):
            BitBrowserClient("http://127.0.0.1:54345").health()


if __name__ == "__main__":
    unittest.main()
