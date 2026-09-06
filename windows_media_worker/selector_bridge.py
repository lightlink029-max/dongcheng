import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class SelectorBridge:
    def __init__(self, store, token, on_change=None, port=0):
        self.store = store
        self.token = token
        self.on_change = on_change
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/selection/submit":
                    return self._reply(404, {"ok": False, "error": "not found"})
                if self.headers.get("X-LightLink-Token") != bridge.token:
                    return self._reply(403, {"ok": False, "error": "invalid token"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 65536:
                        raise ValueError("invalid request size")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    task_id = int(payload["task_id"])
                    if not bridge.store.get_task(task_id):
                        raise ValueError("unknown task")
                    urls = payload.get("urls") or []
                    if not isinstance(urls, list):
                        raise ValueError("urls must be a list")
                    added = bridge.store.add_text(task_id, "\n".join(map(str, urls)))
                    if bridge.on_change:
                        bridge.on_change(task_id, added)
                    self._reply(200, {"ok": True, "added": added})
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    self._reply(400, {"ok": False, "error": str(exc)})

            def _reply(self, status, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

