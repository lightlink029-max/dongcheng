import json
from pathlib import Path


REQUIRED_FIELDS = ("id", "name", "provider", "voice_id", "source")


def default_voice_profiles(windows_voice_names, sherpa_model=""):
    profiles = [{
        "id": "system:" + voice,
        "name": voice,
        "provider": "windows",
        "voice_id": voice,
        "source": "Windows 系统",
        "editable": False,
    } for voice in windows_voice_names]
    profiles.extend(({
        "id": "system:sherpa:0",
        "name": Path(sherpa_model).stem or "Sherpa 默认音色",
        "provider": "sherpa",
        "voice_id": "0",
        "source": "Sherpa 本地模型",
        "editable": False,
    }, {
        "id": "system:volcengine:default",
        "name": "火山引擎默认音色",
        "provider": "volcengine",
        "voice_id": "BV001_streaming",
        "source": "火山引擎",
        "editable": False,
    }))
    return profiles


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
