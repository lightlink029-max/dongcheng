import re
import sqlite3
import json
import uuid
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
                    subtitle_cleanup_policy TEXT NOT NULL DEFAULT 'inherit',
                    subtitle_cleanup_mode TEXT NOT NULL DEFAULT 'quick',
                    subtitle_cleanup_engine TEXT NOT NULL DEFAULT 'sttn',
                    subtitle_cleanup_quality TEXT NOT NULL DEFAULT 'standard',
                    subtitle_quick_method TEXT NOT NULL DEFAULT 'blur',
                    subtitle_region TEXT NOT NULL DEFAULT '5,72,90,22',
                    subtitle_cleaned_path TEXT NOT NULL DEFAULT '',
                    subtitle_cleanup_signature TEXT NOT NULL DEFAULT '',
                    subtitle_cleanup_status TEXT NOT NULL DEFAULT '',
                    subtitle_cleanup_error TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT 'pasted_link',
                    record_kind TEXT NOT NULL DEFAULT 'source',
                    parent_id INTEGER,
                    clip_name TEXT NOT NULL DEFAULT '',
                    clip_type TEXT NOT NULL DEFAULT 'unknown',
                    processed_path TEXT NOT NULL DEFAULT '',
                    processed_kind TEXT NOT NULL DEFAULT '',
                    processing_status TEXT NOT NULL DEFAULT '',
                    processing_error TEXT NOT NULL DEFAULT '',
                    voice_signature TEXT NOT NULL DEFAULT '',
                    storyboard_slot_key TEXT NOT NULL DEFAULT '',
                    library_asset_uuid TEXT NOT NULL DEFAULT '',
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
                "subtitle_cleanup_policy": "TEXT NOT NULL DEFAULT 'inherit'",
                "subtitle_cleanup_mode": "TEXT NOT NULL DEFAULT 'quick'",
                "subtitle_cleanup_engine": "TEXT NOT NULL DEFAULT 'sttn'",
                "subtitle_cleanup_quality": "TEXT NOT NULL DEFAULT 'standard'",
                "subtitle_quick_method": "TEXT NOT NULL DEFAULT 'blur'",
                "subtitle_region": "TEXT NOT NULL DEFAULT '5,72,90,22'",
                "subtitle_cleaned_path": "TEXT NOT NULL DEFAULT ''",
                "subtitle_cleanup_signature": "TEXT NOT NULL DEFAULT ''",
                "subtitle_cleanup_status": "TEXT NOT NULL DEFAULT ''",
                "subtitle_cleanup_error": "TEXT NOT NULL DEFAULT ''",
                "source_kind": "TEXT NOT NULL DEFAULT 'pasted_link'",
                "record_kind": "TEXT NOT NULL DEFAULT 'source'",
                "parent_id": "INTEGER",
                "clip_name": "TEXT NOT NULL DEFAULT ''",
                "clip_type": "TEXT NOT NULL DEFAULT 'unknown'",
                "processed_path": "TEXT NOT NULL DEFAULT ''",
                "processed_kind": "TEXT NOT NULL DEFAULT ''",
                "processing_status": "TEXT NOT NULL DEFAULT ''",
                "processing_error": "TEXT NOT NULL DEFAULT ''",
                "voice_signature": "TEXT NOT NULL DEFAULT ''",
                "storyboard_slot_key": "TEXT NOT NULL DEFAULT ''",
                "library_asset_uuid": "TEXT NOT NULL DEFAULT ''",
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
            connection.execute("""
                CREATE TABLE IF NOT EXISTS local_media_asset (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_uuid TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    preview_path TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    source_task_id INTEGER,
                    source_record_id INTEGER,
                    asset_kind TEXT NOT NULL DEFAULT 'standard_shot',
                    clip_type TEXT NOT NULL DEFAULT 'unknown',
                    role_code TEXT NOT NULL DEFAULT '',
                    role_name TEXT NOT NULL DEFAULT '',
                    track_code TEXT NOT NULL DEFAULT '',
                    track_name TEXT NOT NULL DEFAULT '',
                    scope_code TEXT NOT NULL DEFAULT '',
                    scope_name TEXT NOT NULL DEFAULT '',
                    shot_purpose TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    aspect_ratio TEXT NOT NULL DEFAULT '',
                    duration REAL NOT NULL DEFAULT 0,
                    subtitle_state TEXT NOT NULL DEFAULT 'unchanged',
                    voice_signature TEXT NOT NULL DEFAULT '',
                    copyright_status TEXT NOT NULL DEFAULT 'unreviewed',
                    content_hash TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS storyboard_slot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    slot_key TEXT NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 10,
                    name TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT '',
                    visual_requirement TEXT NOT NULL DEFAULT '',
                    narration TEXT NOT NULL DEFAULT '',
                    target_duration REAL NOT NULL DEFAULT 0,
                    required INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL DEFAULT 'missing',
                    selected_asset_uuid TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, slot_key)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS composition_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    slot_key TEXT NOT NULL,
                    asset_uuid TEXT NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, slot_key)
                )
            """)

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
            connection.execute("DELETE FROM composition_item WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM storyboard_slot WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM render_version WHERE task_id = ?", (int(task_id),))
            connection.execute("DELETE FROM selection_task WHERE task_id = ?", (int(task_id),))

    def add_text(self, task_id, text, source_kind="pasted_link"):
        added = 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            for url in extract_douyin_urls(text):
                existing = connection.execute(
                    "SELECT id FROM selected_video WHERE url = ? AND record_kind = 'source' LIMIT 1",
                    (url,),
                ).fetchone()
                if existing:
                    continue
                order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                    "FROM selected_video",
                ).fetchone()["next_order"]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at, sort_order, source_kind)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (int(task_id), url, extract_video_id(url), now, order, source_kind),
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
                existing = connection.execute(
                    "SELECT id FROM selected_video WHERE url = ? AND record_kind = 'source' LIMIT 1",
                    (url,),
                ).fetchone()
                if existing:
                    continue
                order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                    "FROM selected_video",
                ).fetchone()["next_order"]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO selected_video
                       (task_id, url, video_id, selected_at, status, local_path, caption,
                        sort_order, source_kind)
                       VALUES (?, ?, ?, ?, 'downloaded', ?, ?, ?, 'local_upload')""",
                    (int(task_id), url, path.stem, now, str(path), path.stem, order),
                )
                added += cursor.rowcount
        return added

    def create_clip(self, source_id, trim_start, trim_end, clip_name="", clip_type="unknown"):
        source = self.get_many([source_id])
        if not source:
            raise ValueError("原始素材不存在")
        source = source[0]
        start, end = float(trim_start or 0), float(trim_end or 0)
        if start < 0 or end <= start:
            raise ValueError("片段出点必须大于入点")
        if clip_type not in {"unknown", "talking_face", "face_no_speech", "no_face"}:
            raise ValueError("无效的片段类型")
        parent_id = int(source.get("parent_id") or source["id"])
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        url = "clip://%s/%s" % (parent_id, uuid.uuid4().hex)
        with self._connect() as connection:
            order = connection.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order "
                "FROM selected_video",
            ).fetchone()["next_order"]
            cursor = connection.execute(
                """INSERT INTO selected_video (
                       task_id, url, video_id, selected_at, status, local_path, error,
                       trim_start, trim_end, copyright_status, copyright_note,
                       cover_path, caption, caption_checked, duration, media_checked,
                       sort_order, subtitle_cleanup_policy, subtitle_cleanup_mode,
                       subtitle_cleanup_engine, subtitle_cleanup_quality,
                       subtitle_quick_method, subtitle_region, source_kind, record_kind,
                       parent_id, clip_name, clip_type
                   ) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             ?, 'derived_clip', ?, ?, ?)""",
                (
                    int(source["task_id"]), url, source.get("video_id") or "", now,
                    "downloaded", source.get("local_path") or "", start, end,
                    source.get("copyright_status") or "unreviewed",
                    source.get("copyright_note") or "", source.get("cover_path") or "",
                    source.get("caption") or "", int(source.get("caption_checked") or 0),
                    max(0.0, end - start), int(source.get("media_checked") or 0), order,
                    source.get("subtitle_cleanup_policy") or "inherit",
                    source.get("subtitle_cleanup_mode") or "quick",
                    source.get("subtitle_cleanup_engine") or "sttn",
                    source.get("subtitle_cleanup_quality") or "standard",
                    source.get("subtitle_quick_method") or "blur",
                    source.get("subtitle_region") or "5,72,90,22",
                    source.get("source_kind") or "pasted_link", parent_id,
                    clip_name.strip() or "片段 %.1f-%.1f秒" % (start, end), clip_type,
                ),
            )
            return int(cursor.lastrowid)

    def list(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM selected_video WHERE task_id = ? ORDER BY sort_order, id",
                (int(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_sources(self):
        """Return the workstation-wide raw and derived source library.

        ``task_id`` records where an item was first imported or created. It is
        provenance only; projects reference sources and never own them.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM selected_video
                    WHERE record_kind != 'library_asset'
                    ORDER BY selected_at DESC, id DESC""",
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
            "subtitle_cleanup_policy", "subtitle_cleanup_mode",
            "subtitle_cleanup_engine",
            "subtitle_cleanup_quality", "subtitle_quick_method", "subtitle_region",
            "subtitle_cleaned_path", "subtitle_cleanup_signature",
            "subtitle_cleanup_status", "subtitle_cleanup_error",
            "source_kind", "record_kind", "parent_id", "clip_name", "clip_type",
            "processed_path", "processed_kind", "processing_status",
            "processing_error", "voice_signature", "storyboard_slot_key",
            "library_asset_uuid",
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
            if row["url"].startswith("file:") or row.get("record_kind") == "derived_clip":
                self.update(row["id"], status="downloaded", error="")
            else:
                self.update(
                    row["id"], status="selected", local_path="", error="",
                    caption_checked=0, media_checked=0,
                    subtitle_cleaned_path="", subtitle_cleanup_signature="",
                    subtitle_cleanup_status="", subtitle_cleanup_error="",
                    processed_path="", processed_kind="", processing_status="",
                    processing_error="", voice_signature="",
                )

    def invalidate_processed(self, task_id):
        with self._connect() as connection:
            connection.execute(
                """UPDATE selected_video
                   SET processed_path = '', processed_kind = '', processing_status = '',
                       processing_error = '', voice_signature = ''
                   WHERE task_id = ?""",
                (int(task_id),),
            )

    def delete(self, ids):
        values = [int(value) for value in ids]
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            connection.execute(f"DELETE FROM selected_video WHERE id IN ({placeholders})", values)

    def sync_storyboard(self, task_id, shots):
        """Replace the task storyboard with the locked snapshot supplied by Odoo."""
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        task_id = int(task_id)
        current = {row["slot_key"]: row for row in self.list_storyboard(task_id)}
        normalized = []
        for index, shot in enumerate(shots or [], 1):
            slot_key = str(shot.get("slot_key") or shot.get("key") or shot.get("id") or index)
            previous = current.get(slot_key) or {}
            selected_asset_uuid = str(
                shot.get("selected_asset_uuid") or previous.get("selected_asset_uuid") or ""
            )
            previous_state = str(previous.get("state") or "")
            state = str(shot.get("state") or previous_state or "missing")
            if previous_state in ("ready", "selected"):
                state = previous_state
            if selected_asset_uuid:
                state = "selected" if previous.get("state") == "selected" else "ready"
            normalized.append((
                task_id, slot_key, int(shot.get("sequence") or index * 10),
                str(shot.get("name") or f"分镜 {index}"), str(shot.get("purpose") or ""),
                str(shot.get("visual_requirement") or ""), str(shot.get("narration") or ""),
                float(shot.get("target_duration") or 0), int(bool(shot.get("required", True))),
                state, selected_asset_uuid,
                now, now,
            ))
        with self._connect() as connection:
            connection.execute("DELETE FROM storyboard_slot WHERE task_id = ?", (task_id,))
            connection.executemany(
                """INSERT INTO storyboard_slot (
                       task_id, slot_key, sequence, name, purpose, visual_requirement,
                       narration, target_duration, required, state, selected_asset_uuid,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                normalized,
            )
            connection.execute(
                """DELETE FROM composition_item
                    WHERE task_id = ? AND slot_key NOT IN (
                        SELECT slot_key FROM storyboard_slot WHERE task_id = ?
                    )""",
                (task_id, task_id),
            )

    def list_storyboard(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM storyboard_slot WHERE task_id = ? ORDER BY sequence, id",
                (int(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_storyboard_candidate(self, task_id, slot_key):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE storyboard_slot
                      SET state = CASE WHEN state = 'selected' THEN state ELSE 'ready' END,
                          updated_at = ?
                    WHERE task_id = ? AND slot_key = ?""",
                (now, int(task_id), str(slot_key)),
            )
        if not cursor.rowcount:
            raise ValueError("分镜不存在，请先刷新当前视频项目")

    def register_asset(self, values):
        file_path = str(values.get("file_path") or "")
        if not file_path or not Path(file_path).is_file():
            raise ValueError("素材文件不存在")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        asset_uuid = str(values.get("asset_uuid") or uuid.uuid4())
        metadata = values.get("metadata") or {}
        record = {
            "asset_uuid": asset_uuid,
            "name": str(values.get("name") or Path(file_path).stem),
            "file_path": file_path,
            "preview_path": str(values.get("preview_path") or ""),
            "source_path": str(values.get("source_path") or ""),
            "source_task_id": values.get("source_task_id"),
            "source_record_id": values.get("source_record_id"),
            "asset_kind": str(values.get("asset_kind") or "standard_shot"),
            "clip_type": str(values.get("clip_type") or "unknown"),
            "role_code": str(values.get("role_code") or ""),
            "role_name": str(values.get("role_name") or ""),
            "track_code": str(values.get("track_code") or ""),
            "track_name": str(values.get("track_name") or ""),
            "scope_code": str(values.get("scope_code") or ""),
            "scope_name": str(values.get("scope_name") or ""),
            "shot_purpose": str(values.get("shot_purpose") or ""),
            "language": str(values.get("language") or ""),
            "aspect_ratio": str(values.get("aspect_ratio") or ""),
            "duration": float(values.get("duration") or 0),
            "subtitle_state": str(values.get("subtitle_state") or "unchanged"),
            "voice_signature": str(values.get("voice_signature") or ""),
            "copyright_status": str(values.get("copyright_status") or "unreviewed"),
            "content_hash": str(values.get("content_hash") or ""),
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "active": int(bool(values.get("active", True))),
        }
        columns = list(record)
        assignments = ", ".join(
            f"{column} = excluded.{column}" for column in columns if column != "asset_uuid"
        )
        with self._connect() as connection:
            connection.execute(
                f"""INSERT INTO local_media_asset ({', '.join(columns)}, created_at, updated_at)
                    VALUES ({', '.join('?' for _ in columns)}, ?, ?)
                    ON CONFLICT(asset_uuid) DO UPDATE SET {assignments}, updated_at = excluded.updated_at""",
                [*record.values(), now, now],
            )
        return asset_uuid

    def list_assets(self, active_only=True):
        query = "SELECT * FROM local_media_asset"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY updated_at DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            try:
                value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
            except (TypeError, ValueError):
                value["metadata"] = {}
            result.append(value)
        return result

    def get_asset(self, asset_uuid):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM local_media_asset WHERE asset_uuid = ?", (str(asset_uuid),),
            ).fetchone()
        return dict(row) if row else None

    def select_asset_for_composition(self, task_id, slot_key, asset_uuid):
        task_id, slot_key = int(task_id), str(slot_key or "")
        if not slot_key:
            raise ValueError("请先选择要填充的故事板分镜")
        asset = self.get_asset(asset_uuid)
        if not asset:
            raise ValueError("本地分镜素材库中找不到该素材")
        if asset.get("asset_kind") == "music":
            raise ValueError("背景音乐不能占用视频分镜，请在最终合成设置中选择")
        slots = {row["slot_key"]: row for row in self.list_storyboard(task_id)}
        if slot_key not in slots:
            raise ValueError("故事板分镜不存在，请刷新当前视频项目")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            current = connection.execute(
                "SELECT sequence FROM composition_item WHERE task_id = ? AND slot_key = ?",
                (task_id, slot_key),
            ).fetchone()
            sequence = current["sequence"] if current else connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 10 AS next_sequence "
                "FROM composition_item WHERE task_id = ?", (task_id,),
            ).fetchone()["next_sequence"]
            connection.execute(
                """INSERT INTO composition_item (
                       task_id, slot_key, asset_uuid, sequence, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id, slot_key) DO UPDATE SET
                       asset_uuid = excluded.asset_uuid, updated_at = excluded.updated_at""",
                (task_id, slot_key, str(asset_uuid), int(sequence), now, now),
            )
            connection.execute(
                """UPDATE storyboard_slot
                      SET selected_asset_uuid = ?, state = 'selected', updated_at = ?
                    WHERE task_id = ? AND slot_key = ?""",
                (str(asset_uuid), now, task_id, slot_key),
            )

    def list_composition(self, task_id):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT item.id, item.task_id, item.slot_key, item.asset_uuid,
                          item.sequence, slot.name AS shot_name, slot.purpose AS shot_purpose,
                          slot.required, asset.name, asset.file_path, asset.asset_kind,
                          asset.clip_type, asset.duration, asset.voice_signature,
                          asset.copyright_status, asset.subtitle_state
                     FROM composition_item item
                     JOIN storyboard_slot slot
                       ON slot.task_id = item.task_id AND slot.slot_key = item.slot_key
                     JOIN local_media_asset asset ON asset.asset_uuid = item.asset_uuid
                    WHERE item.task_id = ? AND asset.active = 1
                    ORDER BY item.sequence, item.id""",
                (int(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def move_composition(self, task_id, ids, direction):
        selected = {int(value) for value in ids}
        rows = self.list_composition(task_id)
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
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.executemany(
                "UPDATE composition_item SET sequence = ?, updated_at = ? WHERE id = ?",
                [(index * 10, now, row["id"]) for index, row in enumerate(rows, 1)],
            )

    def remove_composition(self, task_id, ids):
        values = [int(value) for value in ids]
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            slots = connection.execute(
                f"SELECT slot_key FROM composition_item WHERE task_id = ? AND id IN ({placeholders})",
                (int(task_id), *values),
            ).fetchall()
            connection.execute(
                f"DELETE FROM composition_item WHERE task_id = ? AND id IN ({placeholders})",
                (int(task_id), *values),
            )
            connection.executemany(
                """UPDATE storyboard_slot
                      SET selected_asset_uuid = '', state = 'ready', updated_at = ?
                    WHERE task_id = ? AND slot_key = ?""",
                [(now, int(task_id), row["slot_key"]) for row in slots],
            )
