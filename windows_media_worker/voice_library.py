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
)


SHERPA_KOKORO_EN_VOICES = (
    ("AF Default", "0", "美式英语", "女声"),
    ("Bella", "1", "美式英语", "女声"),
    ("Nicole", "2", "美式英语", "女声"),
    ("Sarah", "3", "美式英语", "女声"),
    ("Sky", "4", "美式英语", "女声"),
    ("Adam", "5", "美式英语", "男声"),
    ("Michael", "6", "美式英语", "男声"),
    ("Emma", "7", "英式英语", "女声"),
    ("Isabella", "8", "英式英语", "女声"),
    ("George", "9", "英式英语", "男声"),
    ("Lewis", "10", "英式英语", "男声"),
)


VOLCENGINE_TTS_2_ENGLISH_VOICES = (
    ("Tina老师 2.0", "zh_female_yingyujiaoxue_uranus_bigtts", "中文、英式英语", "教育场景"),
    ("Tim", "en_male_tim_uranus_bigtts", "美式英语", "外语音色"),
    ("Dacey", "en_female_dacey_uranus_bigtts", "美式英语", "外语音色"),
    ("Stokie", "en_female_stokie_uranus_bigtts", "美式英语", "外语音色"),
    ("Charlie 2.0", "ICL_uranus_en_female_charlie_tob", "美式英语", "外语音色"),
    ("Ethan 2.0", "ICL_uranus_en_male_ethan_tob", "澳洲英语", "外语音色"),
    ("Alastor 2.0", "ICL_uranus_en_male_alastor_tob", "英式英语", "外语音色"),
    ("Chucky 2.0", "ICL_uranus_en_male_chucky_tob", "美式英语", "外语音色"),
    ("Noah 2.0", "ICL_uranus_en_male_noah_tob", "美式英语", "外语音色"),
    ("Jigsaw 2.0", "ICL_uranus_en_male_jigsaw_tob", "美式英语", "外语音色"),
    ("Clown Man 2.0", "ICL_uranus_en_male_clown_man_tob", "美式英语", "外语音色"),
    ("Cartoon Chef 2.0", "ICL_uranus_en_male_cartoon_chef_tob", "美式英语", "外语音色"),
    ("Frosty Man 2.0", "ICL_uranus_en_male_frosty_man_tob", "美式英语", "外语音色"),
    ("The Grinch 2.0", "ICL_uranus_en_male_the_grinch_tob", "美式英语", "外语音色"),
    ("Kevin McCallister 2.0", "ICL_uranus_en_male_kevin_mccallister_tob", "美式英语", "外语音色"),
    ("Michael 2.0", "ICL_uranus_en_male_michael_tob", "美式英语", "外语音色"),
    ("Big Boogie 2.0", "ICL_uranus_en_male_big_boogie_tob", "美式英语", "外语音色"),
    ("Xavier 2.0", "ICL_uranus_en_male_xavier_tob", "美式英语", "外语音色"),
    ("Zayne 2.0", "ICL_uranus_en_male_zayne_tob", "美式英语", "外语音色"),
    ("Rowan", "en_male_adam-imitation_uranus_bigtts", "美式英语", "通用场景,有声阅读"),
    ("Alberto", "en_male_alberto_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("Alex", "en_male_alex_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Allison", "en_female_allison_uranus_bigtts", "美式英语", "视频配音"),
    ("Charlotte", "en_female_authoritative-british_uranus_bigtts", "美式英语", "教学场景, 视频配音"),
    ("Margaret", "en_female_authoritative-informative_uranus_bigtts", "美式英语", "通用场景,有声阅读"),
    ("Jones", "en_male_bill-jones_uranus_bigtts", "美式英语", "趣味口音"),
    ("Bill", "en_male_bill_jones_corey_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Brad_Pitt", "en_male_brad_pitt_p1_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Brittney", "en_female_brittney_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Zoe", "en_female_brittney_pimintel_uranus_bigtts", "美式英语", "有声阅读, 客服场景"),
    ("Adrian", "en_male_bruce_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Leo", "en_male_chandler_p1_uranus_bigtts", "美式英语", "趣味口音"),
    ("Bob", "en_male_cowboy-bob_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("John", "en_male_cowboy_john_b_uranus_bigtts", "美式英语", "趣味口音, 角色扮演"),
    ("David", "en_male_david_uranus_bigtts", "美式英语", "通用场景,有声阅读"),
    ("Orion", "en_male_deep-voice_uranus_bigtts", "美式英语", "趣味口音, 角色扮演"),
    ("Julian", "en_male_diyuwenrounan_uranus_bigtts", "美式英语", "有声阅读"),
    ("Harrison", "en_male_evil-guy-oxley_uranus_bigtts", "美式英语", "视频配音"),
    ("Jasper", "en_male_excited-male-voice_uranus_bigtts", "美式英语", "趣味口音"),
    ("Alfred", "en_male_father-christmas_uranus_bigtts", "美式英语", "通用场景,有声阅读, 视频配音"),
    ("Holly", "en_female_female_tutor_ms-jenny_uranus_bigtts", "美式英语", "教学场景, 视频配音"),
    ("Felix", "en_male_fernando-martinez_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("Godfather", "en_male_godfather_uranus_bigtts", "美式英语", "有声阅读, 角色扮演"),
    ("Gollum", "en_male_gollum_uranus_bigtts", "美式英语", "角色扮演"),
    ("Beau", "en_male_hades_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Hayley", "en_female_hayley_uranus_bigtts", "美式英语", "教学场景, 视频配音"),
    ("Jamie", "en_male_jamie_uranus_bigtts", "美式英语", "通用场景, 教学场景, 视频配音"),
    ("Jane", "en_female_jane_uranus_bigtts", "美式英语", "视频配音"),
    ("Jenny", "en_female_jenny_uranus_bigtts", "美式英语", "通用场景, 客服场景"),
    ("Blaze", "en_male_jidongchuanjiaoshi_uranus_bigtts", "美式英语", "趣味口音, 角色扮演"),
    ("Jimmy", "en_male_jimmy_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Joanne", "en_female_joanne_uranus_bigtts", "美式英语", "通用场景,有声阅读, 视频配音"),
    ("Joker", "en_male_joker_uranus_bigtts", "美式英语", "趣味口音, 视频配音"),
    ("Josh", "en_male_josh_uranus_bigtts", "美式英语", "视频配音"),
    ("Josiah", "en_male_josh_coery_uranus_bigtts", "美式英语", "教学场景, 视频配音"),
    ("Kevin", "en_male_kevin_uranus_bigtts", "美式英语", "教学场景, 视频配音"),
    ("Knightley", "en_male_knightley_uranus_bigtts", "美式英语", "有声阅读"),
    ("Lynn", "en_female_lana_del_rey_kelley_d_p1_uranus_bigtts", "美式英语", "角色扮演"),
    ("Ivy", "en_female_lana_del_rey_parky_s_p1_uranus_bigtts", "美式英语", "客服场景"),
    ("Marcus", "en_male_marcus_uranus_bigtts", "美式英语", "通用场景,有声阅读"),
    ("Mel", "en_female_mel_uranus_bigtts", "美式英语", "教学场景, 客服场景"),
    ("Hank", "en_male_michael_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("Chip", "en_male_michael-mouse_uranus_bigtts", "美式英语", "趣味口音, 角色扮演"),
    ("Michael_Kevin", "en_male_michael_kevin_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("Rory", "en_male_motivational-coach_uranus_bigtts", "美式英语", "趣味口音, 视频配音"),
    ("Myra", "en_female_myra_uranus_bigtts", "美式英语", "教学场景"),
    ("Sunny", "en_female_myra_cmb_uranus_bigtts", "美式英语", "教学场景, 客服场景"),
    ("Blair", "en_female_nadia_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Natasha", "en_female_natasha_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Elaine", "en_female_pleasant-female_uranus_bigtts", "美式英语", "有声阅读,视频配音"),
    ("Rachel", "en_female_rachel_p1_uranus_bigtts", "美式英语", "趣味口音"),
    ("Ronald", "en_male_ronald_uranus_bigtts", "美式英语", "有声阅读"),
    ("Russell", "en_male_russell_uranus_bigtts", "美式英语", "通用场景, 教学场景"),
    ("Scarlet", "en_female_scarlet_p1_uranus_bigtts", "美式英语", "客服场景"),
    ("Sharron", "en_female_sharron_uranus_bigtts", "美式英语", "趣味口音"),
    ("Simba", "en_male_simba_p1_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Skye", "en_female_skye_uranus_bigtts", "美式英语", "通用场景"),
    ("Tom", "en_male_tom_hiddleston_p1_uranus_bigtts", "美式英语", "通用场景,有声阅读"),
    ("Valentino", "en_male_valentino_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Clark", "en_male_valentino_corey_uranus_bigtts", "美式英语", "视频配音"),
    ("Megan", "en_female_wenrouzhishijieshuonv_uranus_bigtts", "美式英语", "客服场景"),
    ("Kayla", "en_female_xinwenjieshuonv_uranus_bigtts", "美式英语", "角色扮演"),
    ("Dylan", "en_male_yangguangjieshuonan_uranus_bigtts", "美式英语", "通用场景, 视频配音"),
    ("Zendaya", "en_female_zendaya_p1_uranus_bigtts", "美式英语", "教学场景, 客服场景"),
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
    configured_model = Path(sherpa_model).expanduser() if sherpa_model else None
    if configured_model:
        candidates = (
            configured_model.parent / "kokoro-en-v0_19" / "model.onnx",
            configured_model.parent.parent / "kokoro-en-v0_19" / "model.onnx",
        )
        kokoro_model = next((path for path in candidates if path.is_file()), None)
        if kokoro_model:
            profiles.extend({
                "id": "system:sherpa:kokoro-en-v0_19:" + voice_id,
                "name": "Kokoro " + name,
                "provider": "sherpa",
                "voice_id": voice_id,
                "source": "Sherpa Kokoro 英文模型",
                "source_url": "https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html#kokoro-en-v0-19-english-11-speakers",
                "model_id": str(kokoro_model),
                "language": language,
                "description": description,
                "editable": False,
            } for name, voice_id, language, description in SHERPA_KOKORO_EN_VOICES)
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
    } for name, voice_id, language, description in (
        *VOLCENGINE_TTS_2_VOICES, *VOLCENGINE_TTS_2_ENGLISH_VOICES,
    ))
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
