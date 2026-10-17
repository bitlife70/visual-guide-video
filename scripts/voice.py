"""성우 내레이션 합성.

provider
  edge : Microsoft Edge 신경망 음성 (온라인, 무료, `pip install edge-tts`)
         한국어: ko-KR-SunHiNeural(여), ko-KR-InJoonNeural(남), ko-KR-HyunsuMultilingualNeural(남)
  sapi : Windows 내장 음성 (오프라인, 예: "Microsoft Heami Desktop")

NARRATION = [(t, "문장"), (t, "문장", {"rate": "+10%"}), ...]  — 없으면 SUBTITLES 문구를 그대로 읽는다.
각 문장은 다음 문장 시작 전에 끝나도록 말속도를 최대 +30% 까지 자동으로 올리고,
그래도 넘치면 다음 문장을 뒤로 밀고 리포트에 경고를 남긴다.
"""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile

import numpy as np

from gfx import strip_markup

SR = 44100


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def clean_text(text):
    text = strip_markup(text)
    text = re.sub(r"[\U0001F000-\U0001FFFF☀-➿️‍]", "", text)
    text = text.replace("→", ", ").replace("·", ", ").replace("—", ", ").replace("|", ", ")
    return re.sub(r"\s+", " ", text).strip(" ,")


def _pct(rate):
    return int(str(rate).replace("%", "").replace("+", "") or 0)


def _decode(path):
    raw = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    nz = np.where(np.abs(x) > 0.01)[0]  # 앞뒤 무음 트림
    return x[max(0, nz[0] - 400): nz[-1] + 2000] if len(nz) else x


def _synth_edge(text, voice, rate, out):
    import edge_tts

    async def run():
        await edge_tts.Communicate(text, voice, rate=f"{_pct(rate):+d}%").save(out)

    asyncio.run(run())


def _synth_sapi(text, voice, rate, out):
    r = max(-10, min(10, round(_pct(rate) / 10)))
    ps = (
        "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try {{ $s.SelectVoice('{voice}') }} catch {{}};"
        f"$s.Rate={r};"
        f"$s.SetOutputToWaveFile('{out}');"
        "$s.Speak([Console]::In.ReadToEnd());$s.Dispose()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], input=text.encode("utf-8"), check=True,
                   capture_output=True)


def synth(text, provider, voice, rate, cache_dir):
    key = hashlib.sha1(f"{provider}|{voice}|{rate}|{text}".encode()).hexdigest()[:16]
    os.makedirs(cache_dir, exist_ok=True)
    cpath = os.path.join(cache_dir, key + ".npy")
    if os.path.exists(cpath):
        return np.load(cpath)
    with tempfile.TemporaryDirectory() as td:
        if provider == "edge":
            out = os.path.join(td, "v.mp3")
            _synth_edge(text, voice, rate, out)
        elif provider == "sapi":
            out = os.path.join(td, "v.wav")
            _synth_sapi(text, voice, rate, out)
        else:
            raise ValueError(f"알 수 없는 voice provider: {provider}")
        x = _decode(out)
    np.save(cpath, x)
    return x


def lines_of(tl):
    if tl.narration:
        return [(n[0], n[1], n[2] if len(n) > 2 else {}) for n in tl.narration]
    return [(s[0] + 0.1, s[2], {}) for s in tl.subtitles]


def build_voice(tl, provider=None, voice=None):
    cfg = dict(tl.voice)
    provider = provider or cfg["provider"]
    if voice:
        cfg["voice"] = voice
    elif provider == "sapi" and cfg["voice"].endswith("Neural"):
        cfg["voice"] = "Microsoft Heami Desktop"
    N = int(SR * (tl.duration + 0.5))
    out = np.zeros(N, np.float32)
    lines = sorted(lines_of(tl), key=lambda l: l[0])
    end_limit = tl.duration - 0.4
    cache = os.path.join(tl.build_dir, "voice_cache")
    report, cursor = [], 0.0
    for i, (t, text, opt) in enumerate(lines):
        text = clean_text(text)
        if not text:
            continue
        start = max(t, cursor)
        nxt = lines[i + 1][0] if i + 1 < len(lines) else end_limit
        slot = nxt - start - 0.15
        base = _pct(opt.get("rate", cfg["rate"]))
        x, used = None, base
        for bump in (0, 10, 20, 30):
            used = base + bump
            x = synth(text, provider, opt.get("voice", cfg["voice"]), f"{used:+d}%", cache)
            if len(x) / SR <= slot:
                break
        dur = len(x) / SR
        note = "ok" if dur <= slot else "overflow"
        if start > t + 1e-3:
            note += f" (shifted +{start - t:.2f}s)"
        i0 = int(start * SR)
        seg = x[: max(0, N - i0)]
        out[i0:i0 + len(seg)] += seg
        cursor = start + dur + 0.12
        report.append(dict(t=round(t, 2), start=round(start, 2), end=round(start + dur, 2), slot=round(slot, 2),
                           rate=f"{used:+d}%", status=note, text=text))
    peak = np.abs(out).max()
    if peak > 0:
        out = out / peak * 0.95 * 10 ** (cfg.get("gain_db", 0) / 20)
    os.makedirs(tl.build_dir, exist_ok=True)
    with open(os.path.join(tl.build_dir, "voice_report.json"), "w", encoding="utf-8") as f:
        json.dump(dict(provider=provider, voice=cfg["voice"], lines=report), f, ensure_ascii=False, indent=1)
    return out, report


def duck_curve(voice, depth):
    """보이스가 있는 동안 음악을 낮추는 게인 곡선 (어택 60ms, 릴리즈 350ms)."""
    hop = SR // 100
    n = len(voice) // hop + 1
    env = np.array([np.sqrt(np.mean(voice[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(voice) else 0 for i in range(n)])
    on = (env > 0.02).astype(float)
    sm = np.zeros(n)
    a, r = 1 - np.exp(-1 / 6), 1 - np.exp(-1 / 35)
    v = 0.0
    for i in range(n):
        v += (on[i] - v) * (a if on[i] > v else r)
        sm[i] = v
    g = 1 - depth * sm
    return np.interp(np.arange(len(voice)), np.arange(n) * hop, g)
