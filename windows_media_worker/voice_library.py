import json
from pathlib import Path


REQUIRED_FIELDS = ("id", "name", "provider", "voice_id", "source")


def load_voice_profiles(path):
    path = Path(path)
    if not path.is_file():
        return []
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    return [
        {field: str(item.get(field) or "").strip() for field in REQUIRED_FIELDS}
        for item in values
        if isinstance(item, dict) and all(str(item.get(field) or "").strip() for field in REQUIRED_FIELDS)
    ]


def save_voice_profiles(path, profiles):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [
        {field: str(item.get(field) or "").strip() for field in REQUIRED_FIELDS}
        for item in profiles
    ]
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")

