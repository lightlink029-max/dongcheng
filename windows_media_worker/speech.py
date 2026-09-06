import base64
import importlib.util
import json
import os
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


def windows_voices():
    if os.name != "nt":
        return []
    script = "$s=New-Object -ComObject SAPI.SpVoice; $s.GetVoices() | ForEach-Object {$_.GetDescription()}"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _windows_tts(text, output, voice="", speed=1.0, volume=1.0):
    if os.name != "nt":
        raise RuntimeError("Windows 本地音色仅能在 Windows 上使用")
    text_file = Path(output).with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8-sig")
    rate = max(-10, min(10, int(round((float(speed) - 1) * 5))))
    volume_value = max(0, min(100, int(float(volume) * 100)))
    escaped_voice = voice.replace("'", "''")
    output_value = str(Path(output)).replace("'", "''")
    text_value = str(text_file).replace("'", "''")
    script = (
        "$s=New-Object -ComObject SAPI.SpVoice; "
        f"$s.Rate={rate}; $s.Volume={volume_value}; "
        + (
            f"$selected=$s.GetVoices() | Where-Object {{$_.GetDescription() -eq '{escaped_voice}'}} | Select-Object -First 1; "
            "$s.Voice=$selected; " if voice else ""
        )
        + "$f=New-Object -ComObject SAPI.SpFileStream; "
        + f"$f.Open('{output_value}',3,$false); $s.AudioOutputStream=$f; "
        + f"[void]$s.Speak([IO.File]::ReadAllText('{text_value}')); $f.Close()"
    )
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], check=True)
    finally:
        text_file.unlink(missing_ok=True)
    if not Path(output).is_file() or Path(output).stat().st_size < 128:
        Path(output).unlink(missing_ok=True)
        raise RuntimeError("Windows 本地音色合成失败，请选择已安装的系统音色或配置 sherpa-onnx")
    return Path(output)


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
    app_id = (config.get("volc_app_id") or "").strip()
    token = (config.get("volc_token") or "").strip()
    cluster = (config.get("volc_cluster") or "volcano_tts").strip()
    if not app_id or not token:
        raise RuntimeError("火山引擎配音需要配置 App ID 和 Access Token")
    payload = {
        "app": {"appid": app_id, "token": token, "cluster": cluster},
        "user": {"uid": config.get("volc_uid") or "lightlink-worker"},
        "audio": {
            "voice_type": voice or config.get("volc_default_voice") or "BV001_streaming",
            "encoding": "wav", "speed_ratio": float(speed), "volume_ratio": float(volume),
        },
        "request": {
            "reqid": str(uuid.uuid4()), "text": text, "text_type": "plain",
            "operation": "query",
        },
    }
    response = requests.post(
        config.get("volc_tts_url") or "https://openspeech.bytedance.com/api/v1/tts",
        headers={"Authorization": "Bearer; " + token, "Content-Type": "application/json"},
        json=payload, timeout=300,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") not in (0, 3000):
        raise RuntimeError("火山引擎配音失败：" + str(result.get("message") or result))
    audio = result.get("data")
    if not audio:
        raise RuntimeError("火山引擎没有返回音频数据")
    Path(output).write_bytes(base64.b64decode(audio))
    return Path(output)


def synthesize(config, provider, text, output, voice="", speed=1.0, volume=1.0):
    if provider == "windows":
        return _windows_tts(text, output, voice, speed, volume)
    if provider == "sherpa":
        return _sherpa_tts(config, text, output, voice, speed, volume)
    if provider == "volcengine":
        return _volcengine_tts(config, text, output, voice, speed, volume)
    raise ValueError("不支持的配音服务：" + str(provider))
