import sys
from pathlib import Path

from faster_whisper import WhisperModel


def srt_time(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: whisper_srt.py INPUT_VIDEO OUTPUT_SRT SOURCE_LANGUAGE")
    source, output, language = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    root = Path(__file__).resolve().parent
    model_name = (root / "model-name.txt").read_text(encoding="utf-8-sig").strip() or "small"
    language_codes = {
        "Chinese": "zh", "中文": "zh", "English": "en", "英语": "en",
        "Japanese": "ja", "日语": "ja", "Korean": "ko", "韩语": "ko",
    }
    model = WhisperModel(
        model_name, device="cpu", compute_type="int8",
        download_root=str(root / "models"),
    )
    segments, _ = model.transcribe(
        str(source), language=language_codes.get(language), vad_filter=True,
    )
    lines = []
    for index, segment in enumerate(segments, 1):
        text = segment.text.strip()
        if text:
            lines.extend([
                str(index), f"{srt_time(segment.start)} --> {srt_time(segment.end)}", text, "",
            ])
    if not lines:
        raise RuntimeError("没有从视频中识别到语音")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
