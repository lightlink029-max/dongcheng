import json
from pathlib import Path


REQUIRED_FIELDS = ("id", "name", "provider", "voice_id", "source")
OPTIONAL_FIELDS = ("source_url",)


def default_voice_profiles(sherpa_model=""):
    return [{
        "id": "system:sherpa:0",
        "name": Path(sherpa_model).stem or "Sherpa 默认音色",
        "provider": "sherpa",
        "voice_id": "0",
        "source": "Sherpa 本地模型",
        "source_url": "https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/index.html",
        "editable": False,
    }, {
        "id": "system:volcengine:default",
        "name": "火山引擎默认音色",
        "provider": "volcengine",
        "voice_id": "zh_female_vv_uranus_bigtts",
        "source": "火山引擎豆包语音合成",
        "source_url": "https://docs.volcengine.com/docs/6561/2532486?lang=zh",
        "editable": False,
    }]


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
        {
            field: str(item.get(field) or "").strip()
            for field in REQUIRED_FIELDS + OPTIONAL_FIELDS
        }
        for item in values
        if isinstance(item, dict) and all(str(item.get(field) or "").strip() for field in REQUIRED_FIELDS)
    ]


def save_voice_profiles(path, profiles):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [
        {
            field: str(item.get(field) or "").strip()
            for field in REQUIRED_FIELDS + OPTIONAL_FIELDS
        }
        for item in profiles
    ]
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
