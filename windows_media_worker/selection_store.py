import re
import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import parse_qs, urlparse


DOUYIN_HOSTS = {"douyin.com", "www.douyin.com", "v.douyin.com", "v.iesdouyin.com"}
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def extract_douyin_urls(text):
    urls, seen = [], set()
    for raw in URL_PATTERN.findall(text or ""):
        url = raw.rstrip(".,;，。；!！?？)]}")
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            continue
        if host not in DOUYIN_HOSTS or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def extract_video_id(url):
    parsed = urlparse(url or "")
    match = re.search(r"/(?:video|note)/(\d+)", parsed.path)
    if match:
        return match.group(1)
    query = parse_qs(parsed.query)
    for key in ("modal_id", "aweme_id", "item_id"):
        value = query.get(key, [""])[0]
        if value.isdigit():
            return value
    return ""


class SelectionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self):
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS selected_video (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    video_id TEXT NOT NULL DEFAULT '',
                    selected_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'selected',
                    local_path TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    UNIQUE(task_id, url)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS selection_task (
                    task_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'processing',
                    updated_at TEXT NOT NULL,
                    result_path TEXT NOT NULL DEFAULT '',
                    subtitle_path TEXT NOT NULL DEFAULT ''
                )
            """)
            columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(selection_task)"
                ).fetchall()
            }
            for name in ("result_path", "subtitle_path"):
                if name not in columns:
                    connection.execute(
                        "ALTER TABLE selection_task ADD COLUMN %s TEXT NOT NULL DEFAULT ''" % name
                    )

    def next_local_task_id(self):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MIN(task_id) AS minimum FROM selection_task WHERE task_id < 0"
            ).fetchone()
        return min(-1, int(row["minimum"] or 0) - 1)

    def save_task(self, task, status="processing"):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO selection_task (task_id, payload, status, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       payload = excluded.payload, status = excluded.status,
                       updated_at = excluded.updated_at""",
                (int(task["id"]), json.dumps(task, ensure_ascii=False), status, now),
            )

    def set_task_status(self, task_id, status):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "UPDATE selection_task SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, now, int(task_id)),
            )

    def list_tasks(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM selection_task ORDER BY updated_at DESC, task_id DESC",
            ).fetchall()
        result = []
        for row in rows:
            task = json.loads(row["payload"])
            task.update({
                "local_status": row["status"], "result_path": row["result_path"],
                "subtitle_path": row["subtitle_path"],
            })
            result.append(task)
        return result

    def get_task(self, task_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM selection_task WHERE task_id = ?", (int(task_id),),
            ).fetchone()
        if not row:
            return None
        task = json.loads(row["payload"])
        task.update({
            "local_status": row["status"], "result_path": row["result_path"],
            "subtitle_path": row["subtitle_path"],
        })
        return task

    def update_task(self, task, status=None):
        current = self.get_task(task["id"])
        self.save_task(task, status=status or (current or {}).get("local_status", "processing"))

    def set_task_result(self, task_id, result_path, subtitle_path="", status="ready_review"):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """UPDATE selection_task
                      SET result_path = ?, subtitle_path = ?, status = ?, updated_at = ?
                    WHERE task_id = ?""",
                (str(result_path or ""), str(subtitle_path or ""), status, now, int(task_id)),
            )

    def delete_task(self, task_id):
        with self._connect() as connection:
            connection.execute("DELETE FROM selected_video WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM selection_task WHERE task_id = ?", (int(task_id),))

    def add_text(self, task_id, text):
        added = 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            for url in extract_douyin_urls(text):
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at) VALUES (?, ?, ?, ?)""",
                    (int(task_id), url, extract_video_id(url), now),
                )
                added += cursor.rowcount
        return added

    def add_local_files(self, task_id, paths):
        added = 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            for value in paths:
                path = Path(value).expanduser().resolve()
                if not path.is_file():
                    continue
                url = path.as_uri()
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at, status, local_path)
                       VALUES (?, ?, ?, ?, 'downloaded', ?)""",
                    (int(task_id), url, path.stem, now, str(path)),
                )
                added += cursor.rowcount
        return added

    def list(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM selected_video WHERE task_id = ? ORDER BY id", (int(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_many(self, ids):
        values = [int(value) for value in ids]
        if not values:
            return []
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM selected_video WHERE id IN ({placeholders}) ORDER BY id", values,
            ).fetchall()
        return [dict(row) for row in rows]

    def update(self, record_id, **values):
        allowed = {"video_id", "status", "local_path", "error"}
        values = {key: str(value or "") for key, value in values.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE selected_video SET {assignments} WHERE id = ?",
                [*values.values(), int(record_id)],
            )

    def reset_download(self, ids):
        for row in self.get_many(ids):
            if row["url"].startswith("file:"):
                self.update(row["id"], status="downloaded", error="")
            else:
                self.update(row["id"], status="selected", local_path="", error="")

    def delete(self, ids):
        values = [int(value) for value in ids]
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            connection.execute(f"DELETE FROM selected_video WHERE id IN ({placeholders})", values)
