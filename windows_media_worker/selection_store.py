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
                    trim_start REAL NOT NULL DEFAULT 0,
                    trim_end REAL NOT NULL DEFAULT 0,
                    copyright_status TEXT NOT NULL DEFAULT 'unreviewed',
                    copyright_note TEXT NOT NULL DEFAULT '',
                    cover_path TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    caption_checked INTEGER NOT NULL DEFAULT 0,
                    duration REAL NOT NULL DEFAULT 0,
                    media_checked INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(task_id, url)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS render_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    version_no INTEGER NOT NULL,
                    result_path TEXT NOT NULL,
                    subtitle_path TEXT NOT NULL DEFAULT '',
                    source_video_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, version_no)
                )
            """)
            render_columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(render_version)"
                ).fetchall()
            }
            if "source_video_ids" not in render_columns:
                connection.execute(
                    "ALTER TABLE render_version ADD COLUMN source_video_ids "
                    "TEXT NOT NULL DEFAULT '[]'"
                )
            video_columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(selected_video)"
                ).fetchall()
            }
            video_additions = {
                "trim_start": "REAL NOT NULL DEFAULT 0",
                "trim_end": "REAL NOT NULL DEFAULT 0",
                "copyright_status": "TEXT NOT NULL DEFAULT 'unreviewed'",
                "copyright_note": "TEXT NOT NULL DEFAULT ''",
                "cover_path": "TEXT NOT NULL DEFAULT ''",
                "caption": "TEXT NOT NULL DEFAULT ''",
                "caption_checked": "INTEGER NOT NULL DEFAULT 0",
                "duration": "REAL NOT NULL DEFAULT 0",
                "media_checked": "INTEGER NOT NULL DEFAULT 0",
                "sort_order": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in video_additions.items():
                if name not in video_columns:
                    connection.execute(
                        f"ALTER TABLE selected_video ADD COLUMN {name} {definition}"
                    )
            connection.execute(
                "UPDATE selected_video SET sort_order = id WHERE sort_order = 0"
            )
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

    def set_task_result(
        self, task_id, result_path, subtitle_path="", status="ready_review", version_no=None,
        source_video_ids=None,
    ):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """UPDATE selection_task
                      SET result_path = ?, subtitle_path = ?, status = ?, updated_at = ?
                    WHERE task_id = ?""",
                (str(result_path or ""), str(subtitle_path or ""), status, now, int(task_id)),
            )
            if version_no is None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(version_no), 0) + 1 AS next_version "
                    "FROM render_version WHERE task_id = ?", (int(task_id),),
                ).fetchone()
                version_no = row["next_version"]
            connection.execute(
                """INSERT INTO render_version
                   (task_id, version_no, result_path, subtitle_path, source_video_ids, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (int(task_id), int(version_no), str(result_path or ""),
                 str(subtitle_path or ""), json.dumps(source_video_ids or []), now),
            )

    def next_render_version(self, task_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 AS next_version "
                "FROM render_version WHERE task_id = ?", (int(task_id),),
            ).fetchone()
        return int(row["next_version"])

    def list_versions(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM render_version WHERE task_id = ? ORDER BY version_no DESC",
                (int(task_id),),
            ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            try:
                value["source_video_ids"] = json.loads(value.get("source_video_ids") or "[]")
            except (TypeError, ValueError):
                value["source_video_ids"] = []
            result.append(value)
        return result

    def delete_versions(self, task_id, version_ids):
        values = sorted({int(value) for value in version_ids})
        if not values:
            return []
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            placeholders = ",".join("?" for _value in values)
            deleted = connection.execute(
                f"SELECT * FROM render_version WHERE task_id = ? AND id IN ({placeholders})",
                (int(task_id), *values),
            ).fetchall()
            if not deleted:
                return []
            connection.execute(
                f"DELETE FROM render_version WHERE task_id = ? AND id IN ({placeholders})",
                (int(task_id), *values),
            )
            latest = connection.execute(
                "SELECT * FROM render_version WHERE task_id = ? ORDER BY version_no DESC LIMIT 1",
                (int(task_id),),
            ).fetchone()
            connection.execute(
                """UPDATE selection_task
                      SET result_path = ?, subtitle_path = ?, status = ?, updated_at = ?
                    WHERE task_id = ?""",
                (
                    latest["result_path"] if latest else "",
                    latest["subtitle_path"] if latest else "",
                    "ready_review" if latest else "downloaded",
                    now, int(task_id),
                ),
            )
        return [dict(row) for row in deleted]

    def delete_version(self, task_id, version_id):
        deleted = self.delete_versions(task_id, [version_id])
        return deleted[0] if deleted else None

    def delete_task(self, task_id):
        with self._connect() as connection:
            connection.execute("DELETE FROM selected_video WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM render_version WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM selection_task WHERE task_id = ?", (int(task_id),))

    def add_text(self, task_id, text):
        added = 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            for url in extract_douyin_urls(text):
                order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                    "FROM selected_video WHERE task_id = ?", (int(task_id),),
                ).fetchone()["next_order"]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at, sort_order)
                       VALUES (?, ?, ?, ?, ?)""",
                    (int(task_id), url, extract_video_id(url), now, order),
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
                order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                    "FROM selected_video WHERE task_id = ?", (int(task_id),),
                ).fetchone()["next_order"]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at, status, local_path, caption, sort_order)
                       VALUES (?, ?, ?, ?, 'downloaded', ?, ?, ?)""",
                    (int(task_id), url, path.stem, now, str(path), path.stem, order),
                )
                added += cursor.rowcount
        return added

    def list(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM selected_video WHERE task_id = ? ORDER BY sort_order, id",
                (int(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_many(self, ids):
        values = [int(value) for value in ids]
        if not values:
            return []
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM selected_video WHERE id IN ({placeholders}) ORDER BY sort_order, id",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_selected(self, task_id, ids=None):
        rows = self.list(task_id)
        if ids is None:
            return rows
        selected = {int(value) for value in ids}
        return [row for row in rows if row["id"] in selected]

    def move(self, task_id, ids, direction):
        selected = {int(value) for value in ids}
        rows = self.list(task_id)
        if not selected or direction not in (-1, 1):
            return
        if direction < 0:
            for index in range(1, len(rows)):
                if rows[index]["id"] in selected and rows[index - 1]["id"] not in selected:
                    rows[index - 1], rows[index] = rows[index], rows[index - 1]
        else:
            for index in range(len(rows) - 2, -1, -1):
                if rows[index]["id"] in selected and rows[index + 1]["id"] not in selected:
                    rows[index], rows[index + 1] = rows[index + 1], rows[index]
        with self._connect() as connection:
            connection.executemany(
                "UPDATE selected_video SET sort_order = ? WHERE id = ?",
                [(index, row["id"]) for index, row in enumerate(rows, 1)],
            )

    def update(self, record_id, **values):
        allowed = {
            "video_id", "status", "local_path", "error", "trim_start", "trim_end",
            "copyright_status", "copyright_note", "cover_path", "caption",
            "caption_checked", "duration",
            "media_checked",
        }
        values = {key: value for key, value in values.items() if key in allowed}
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
                self.update(
                    row["id"], status="selected", local_path="", error="",
                    caption_checked=0, media_checked=0,
                )

    def delete(self, ids):
        values = [int(value) for value in ids]
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            connection.execute(f"DELETE FROM selected_video WHERE id IN ({placeholders})", values)
