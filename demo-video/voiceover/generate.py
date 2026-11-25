"""Generate the voiceover with Piper (free, offline neural TTS) and write durations.json.

    pip install piper-tts
    python -m piper.download_voices en_US-lessac-high --download-dir voiceover/voices
    python voiceover/generate.py            # from demo-video/
"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "public" / "voiceover"
script = json.loads((HERE / "script.json").read_text())
voices = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "voices"
model = voices / f"{script['voice']}.onnx"
OUT.mkdir(parents=True, exist_ok=True)
durations = {}
for scene, text in script["lines"].items():
    slug = re.sub(r"[^a-z0-9]+", "-", scene.lower()).strip("-")
    wav = OUT / f"{slug}.wav"
    subprocess.run([sys.executable, "-m", "piper", "-m", str(model), "-f", str(wav), "--length-scale", "0.95",
                    "--sentence-silence", "0.25", "--", text], check=True, capture_output=True)
    with wave.open(str(wav)) as w:
        durations[scene] = round(w.getnframes() / w.getframerate(), 2)
    mp3 = wav.with_suffix(".mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "128k", str(mp3)], check=True)
    wav.unlink()
    print(f"{scene:20s} {durations[scene]:5.2f}s  {slug}.mp3")
(HERE.parent / "src" / "voiceover.json").write_text(json.dumps(durations, indent=2) + "\n")
