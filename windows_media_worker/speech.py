import base64
import importlib.util
import json
import subprocess
import uuid
from pathlib import Path

import requests


def asr_available(config):
    command = (config.get("whisper_command") or "").strip()
    return bool(command and Path(command).expanduser().is_file()) or importlib.util.find_spec("faster_whisper") is not None


def srt_time(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe(config, source_video, output_srt, language="Chinese"):
    """Transcribe with an explicitly configured command or an installed faster-whisper."""
    command = (config.get("whisper_command") or "").strip()
    if command:
        executable = Path(command).expanduser()
        if not executable.is_file():
            raise RuntimeError(f"语音识别程序不存在：{executable}")
        subprocess.run(
            [str(executable), str(source_video), str(output_srt), str(language)],
            check=True,
        )
        if not Path(output_srt).is_file():
            raise RuntimeError("本地语音识别程序没有生成 SRT 文件")
        return Path(output_srt)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    model_name = (config.get("whisper_model") or "small").strip()
    model_dir = (config.get("whisper_model_dir") or "").strip() or None
    model = WhisperModel(
        model_name,
        device=(config.get("whisper_device") or "cpu"),
        compute_type=(config.get("whisper_compute_type") or "int8"),
        download_root=model_dir,
    )
    language_codes = {
        "Chinese": "zh", "中文": "zh", "English": "en", "英语": "en",
        "Japanese": "ja", "日语": "ja", "Korean": "ko", "韩语": "ko",
    }
    segments, _info = model.transcribe(
        str(source_video), language=language_codes.get(language), vad_filter=True,
    )
    lines = []
    for index, segment in enumerate(segments, 1):
        text = segment.text.strip()
        if text:
            lines.extend([
                str(index), f"{srt_time(segment.start)} --> {srt_time(segment.end)}", text, "",
            ])
    if not lines:
        raise RuntimeError("没有从原视频中识别到可用语音")
    Path(output_srt).write_text("\n".join(lines), encoding="utf-8")
    return Path(output_srt)


def _sherpa_tts(config, text, output, voice="", speed=1.0, _volume=1.0):
    values = [
        config.get("sherpa_command"), config.get("sherpa_model"),
        config.get("sherpa_tokens"), config.get("sherpa_data_dir"),
    ]
    if not all(str(value or "").strip() for value in values):
        raise RuntimeError("sherpa-onnx 尚未完整配置：程序、模型、tokens 和 data-dir 均为必填")
    executable, model, tokens, data_dir = [Path(value).expanduser() for value in values]
    missing = [
        str(path) for path, valid in (
            (executable, executable.is_file()), (model, model.is_file()),
            (tokens, tokens.is_file()), (data_dir, data_dir.is_dir()),
        ) if not valid
    ]
    if missing:
        raise RuntimeError("sherpa-onnx 尚未完整配置：" + "、".join(missing))
    command = [
        str(executable), f"--vits-model={model}", f"--vits-tokens={tokens}",
        f"--vits-data-dir={data_dir}", f"--output-filename={output}",
        f"--vits-length-scale={1 / max(0.25, float(speed))}",
    ]
    if str(voice).isdigit():
        command.append(f"--sid={voice}")
    command.append(text)
    subprocess.run(command, check=True)
    return Path(output)


def _volcengine_tts(config, text, output, voice="", speed=1.0, volume=1.0):
    api_key = (config.get("volc_api_key") or "").strip()
    resource_id = (config.get("volc_resource_id") or "seed-tts-2.0").strip()
    if not api_key:
        raise RuntimeError("火山引擎配音需要配置新版 API Key")
    speaker = voice or config.get("volc_default_voice") or "zh_female_vv_uranus_bigtts"
    speech_rate = max(-50, min(100, int(round((float(speed) - 1) * 100))))
    loudness_rate = max(-50, min(100, int(round((float(volume) - 1) * 100))))
    payload = {
        "user": {"uid": config.get("volc_uid") or "lightlink-worker"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "sample_rate": 24000,
            "audio_params": {
                "format": "mp3",
                "speech_rate": speech_rate,
                "loudness_rate": loudness_rate,
                "bit_rate": 64000,
            },
        },
    }
    request_id = str(uuid.uuid4())
    response = requests.post(
        config.get("volc_tts_url") or "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": request_id,
        },
        json=payload, timeout=300, stream=True,
    )
    chunks = []
    last_result = None
    try:
        if response.status_code >= 400:
            detail = (response.text or "").strip()[:500]
            raise RuntimeError(
                f"火山引擎配音请求失败（HTTP {response.status_code}）："
                + (detail or "请检查 API Key、Resource ID、音色权限和账户余额")
            )
        for line in response.iter_lines(decode_unicode=True):
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            if not line or not line.startswith("data:"):
                continue
            result = json.loads(line[5:].strip())
            last_result = result
            code = result.get("code")
            if str(code) not in ("None", "0", "20000000"):
                raise RuntimeError("火山引擎配音失败：" + str(result.get("message") or result))
            if result.get("data"):
                chunks.append(base64.b64decode(result["data"]))
    finally:
        response.close()
    if not chunks:
        log_id = response.headers.get("X-Tt-Logid", "")
        detail = (last_result or {}).get("message") or "响应中没有音频分片"
        raise RuntimeError(
            f"火山引擎没有返回音频：{detail}；Resource ID={resource_id}；"
            f"音色 ID={speaker}；Log ID={log_id or request_id}"
        )
    output = Path(output).with_suffix(".mp3")
    output.write_bytes(b"".join(chunks))
    return output


def synthesize(config, provider, text, output, voice="", speed=1.0, volume=1.0):
    if provider == "sherpa":
        return _sherpa_tts(config, text, output, voice, speed, volume)
    if provider == "volcengine":
        return _volcengine_tts(config, text, output, voice, speed, volume)
    raise ValueError("不支持的配音服务：" + str(provider))
