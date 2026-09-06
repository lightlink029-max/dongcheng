import json
from pathlib import Path


REQUIRED_FIELDS = ("id", "name", "provider", "voice_id", "source")
OPTIONAL_FIELDS = ("source_url", "model_id", "language", "description")


VOLCENGINE_TTS_2_VOICES = (
    ("Vivi 2.0", "zh_female_vv_uranus_bigtts", "中文 / English", "通用场景"),
    ("大壹", "zh_male_dayi_saturn_bigtts", "中文", "视频配音"),
    ("黑猫侦探社咪仔", "zh_female_mizai_saturn_bigtts", "中文", "视频配音"),
    ("鸡汤女", "zh_female_jitangnv_saturn_bigtts", "中文", "视频配音"),
    ("魅力女友", "zh_female_meilinvyou_saturn_bigtts", "中文", "视频配音"),
    ("流畅女声", "zh_female_santongyongns_saturn_bigtts", "中文", "视频配音"),
    ("儒雅逸辰", "zh_male_ruyayichen_saturn_bigtts", "中文", "视频配音"),
    ("可爱女生", "ICL_zh_female_keainvsheng_tob", "中文", "角色扮演"),
    ("调皮公主", "ICL_zh_female_tiaopigongzhu_tob", "中文", "角色扮演"),
    ("儿童绘本", "zh_female_xueayi_saturn_bigtts", "中文", "有声阅读"),
    ("Michael 2.0", "ICL_uranus_en_male_michael_tob", "English (US)", "通用男声"),
)


def default_voice_profiles(sherpa_model="", volc_resource_id="seed-tts-2.0"):
    profiles = [{
        "id": "system:sherpa:0",
        "name": Path(sherpa_model).stem or "Sherpa 默认音色",
        "provider": "sherpa",
        "voice_id": "0",
        "source": "Sherpa 本地模型",
        "source_url": "https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/index.html",
        "model_id": sherpa_model,
        "language": "取决于本地模型",
        "description": "当前配置的 sherpa-onnx VITS 模型",
        "editable": False,
    }]
    profiles.extend({
        "id": "system:volcengine:" + voice_id,
        "name": name,
        "provider": "volcengine",
        "voice_id": voice_id,
        "source": "火山引擎豆包语音合成 2.0",
        "source_url": "https://www.volcengine.com/docs/6561/1257544?lang=zh",
        "model_id": volc_resource_id or "seed-tts-2.0",
        "language": language,
        "description": description,
        "editable": False,
    } for name, voice_id, language, description in VOLCENGINE_TTS_2_VOICES)
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
