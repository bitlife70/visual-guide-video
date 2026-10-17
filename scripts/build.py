"""영상 → 비주얼 가이드/하이라이트 영상 빌드.

  python build.py TIMELINE.py                         # 음악 + 효과음 + (원본 소리) + 영상
  python build.py TIMELINE.py --voice edge            # + 성우 내레이션 (Edge 신경망)
  python build.py TIMELINE.py --voice sapi            # + 성우 내레이션 (Windows 오프라인)
  python build.py TIMELINE.py --preview 3.5,7.4,26    # 원본 시각의 프레임 미리보기 (+2x2 시트)
  python build.py TIMELINE.py --preview-out 12,30     # 출력 시각 기준 미리보기 (슬로모션·정지 확인용)
  python build.py TIMELINE.py --audio-only            # 오디오만
  python build.py TIMELINE.py --workers 8             # 병렬 렌더링 프로세스 수 (기본: CPU 수에 맞춤)
"""
import argparse
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import wave

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _canvas_env():
    """엔진을 import 하기 전에 timeline.py 의 CANVAS (예: (1080, 1920) 세로 쇼츠) 를 환경변수로 넘긴다 (병렬 프로세스도 상속)."""
    import re
    for a in sys.argv[1:]:
        if a.endswith(".py") and os.path.exists(a):
            m = re.search(r"^CANVAS\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", open(a, encoding="utf-8").read(), re.M)
            if m:
                os.environ["VGUIDE_CANVAS"] = f"{m.group(1)}x{m.group(2)}"
            break


_canvas_env()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import music  # noqa: E402
import render  # noqa: E402
import tl as tlmod  # noqa: E402
from gfx import strip_markup  # noqa: E402
from sheet import make_sheets  # noqa: E402

SR = music.SR


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def write_wav(path, x, dur):
    x = x[:, : int(dur * SR)]
    pcm = (np.clip(x.T, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ================================================================ audio
def source_audio(tl, N):
    """원본 소리를 출력 시간축으로 리매핑 (슬로모션은 피치가 내려가고, 정지 구간은 무음)."""
    r = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", tl.src, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    raw = np.frombuffer(r.stdout, "<f4")
    if raw.size < 2:
        return None
    src = raw.reshape(-1, 2).T
    tau = np.arange(N) / SR
    ts = tl.remap.src_array(tau)
    pos = ts * SR
    out = np.stack([np.interp(pos, np.arange(src.shape[1]), c, right=0) for c in src])
    # 정지 구간 무음 (20ms 페이드)
    rate = np.gradient(ts) * SR
    g = (rate > 0.05).astype(np.float64)
    # 빨리감기(1.8배 이상) 구간은 다람쥐 목소리가 되므로 줄인다 (SOURCE_AUDIO['fast_gain'], 기본 0.3)
    g *= np.where(rate > 1.8, tl.source_audio.get("fast_gain", 0.3), 1.0)
    k = int(0.05 * SR)
    g = np.convolve(g, np.ones(k) / k, mode="same")
    return out * g[None, :]


def limiter(x, ceil=0.95):
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    env = np.abs(x).max(axis=0)
    red = 1 - np.minimum(1, ceil / (env + 1e-9))
    red = maximum_filter1d(red, int(0.012 * SR))
    red = uniform_filter1d(red, int(0.012 * SR))
    y = x * (1 - red)[None, :]
    return np.tanh(y / ceil) * ceil


def build_audio(tl, voice_provider, voice_name, no_music):
    N = int(SR * (tl.duration + 0.5))
    mus = np.zeros((2, N))
    if tl.music.get("enabled", True) and not no_music:
        mus, sec, bar = music.build_music(tl)
        print(f"[music] {tl.music.get('style')} · bar={bar:.3f}s · sections(bar)={sec}")
        mus = mus * tl.music.get("volume", 0.82)
    fx = music.build_sfx(tl) * tl.sfx_volume
    src = np.zeros((2, N))
    if tl.source_audio.get("enabled"):
        s = source_audio(tl, N)
        if s is not None:
            src = s * tl.source_audio.get("volume", 1.0)
            print(f"[source audio] volume {tl.source_audio.get('volume', 1.0)}")
    vx = np.zeros(N)
    g = np.ones(N)
    if voice_provider and voice_provider != "none":
        import voice
        vx, report = voice.build_voice(tl, voice_provider, voice_name)
        g = voice.duck_curve(vx, tl.music.get("duck", 0.55))
        bad = [r for r in report if r["status"] != "ok"]
        print(f"[voice] {voice_provider} · {len(report)}문장 · 경고 {len(bad)}건 → build/voice_report.json")
        for r in bad:
            print(f"   ! {r['t']:6.2f}s {r['status']:<24} slot={r['slot']}s  dur={r['end'] - r['start']:.2f}s  {r['text'][:40]}")
    gs = 1 - (1 - g) * tl.source_audio.get("duck", 0.8)
    mix = mus * g[None, :] + fx * (0.6 + 0.4 * g[None, :]) + src * gs[None, :] + np.stack([vx, vx])
    mix = limiter(mix * 10 ** (tl.master_gain_db / 20))
    os.makedirs(tl.build_dir, exist_ok=True)
    path = os.path.join(tl.build_dir, "audio.wav")
    write_wav(path, mix, tl.duration)
    return path


def write_srt(tl, path):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(tl.subtitles, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{strip_markup(text)}\n\n")


# ================================================================ video
class Reader:
    """단조 증가하는 원본 프레임 번호를 순서대로 읽는다 (건너뛸 땐 grab)."""

    def __init__(self, path, n_frames):
        self.cap = cv2.VideoCapture(path)
        self.n = n_frames
        self.pos = -1
        self.frame = None

    def get(self, idx):
        idx = min(max(idx, 0), self.n - 1)
        if self.frame is not None and idx == self.pos:
            return self.frame
        if self.pos < 0 or idx < self.pos or idx - self.pos > 90:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            self.pos = idx - 1
        while self.pos < idx - 1:
            self.cap.grab()
            self.pos += 1
        ok, fr = self.cap.read()
        if ok:
            self.frame, self.pos = fr, idx
        return self.frame


def source_frame(rd, tl, t):
    """출력 시각 t 의 원본 프레임. 빨리감기(원본 2프레임 이상 건너뜀) 구간은 그 사이 프레임을 평균해 모션블러를 준다."""
    ts = tl.remap.src(t)
    if tl.speed_blend:
        a, b = tl.remap.src(max(0.0, t - 0.5 / tl.fps)), tl.remap.src(t + 0.5 / tl.fps)
        i0, i1 = int(round(a * tl.fps_src)), int(round(b * tl.fps_src))
        if i1 - i0 >= 2:
            idxs = sorted(set(np.linspace(i0, i1 - 1, min(8, i1 - i0)).round().astype(int).tolist()))
            acc = None
            for i in idxs:
                f = rd.get(i).astype(np.float32)
                acc = f if acc is None else acc + f
            return (acc / len(idxs)).astype(np.uint8)
    return rd.get(int(round(ts * tl.fps_src)))


def _encoder(tl, out, size, fps):
    return [ffmpeg_exe(), "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}", "-r", f"{fps:.6f}", "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(tl.quality), "-pix_fmt", "yuv420p", out]


def _render_range(args):
    timeline, k0, k1, out, wid = args
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tl = tlmod.load(timeline)
    render.setup(tl)
    size = tl.output_size
    proc = subprocess.Popen(_encoder(tl, out, size, tl.fps), stdin=subprocess.PIPE)
    rd = Reader(tl.src, tl.info["frames"])
    done = 0
    try:
        for k in range(k0, k1):
            t = k / tl.fps
            img = render.render_frame(source_frame(rd, tl, t), t)
            if (img.shape[1], img.shape[0]) != size:
                img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
            proc.stdin.write(img.tobytes())
            done += 1
            if done % 200 == 0:
                print(f"  [w{wid}] {done}/{k1 - k0}", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"worker {wid}: ffmpeg 인코딩 실패")
    return done


def render_video(tl, audio, workers):
    os.makedirs(os.path.dirname(tl.output), exist_ok=True)
    n = int(round(tl.duration * tl.fps))
    workers = max(1, min(workers, n // 60 or 1))
    tmp = tempfile.mkdtemp(prefix="vg_", dir=tl.build_dir)
    bounds = np.linspace(0, n, workers + 1).astype(int)
    jobs = [(tl.timeline_path, int(bounds[i]), int(bounds[i + 1]), os.path.join(tmp, f"seg{i:02d}.mp4"), i)
            for i in range(workers)]
    print(f"[render] {n} frames · {tl.fps:g}fps · {tl.output_size[0]}x{tl.output_size[1]} · workers={workers}")
    if workers == 1:
        counts = [_render_range(jobs[0])]
    else:
        with mp.get_context("spawn").Pool(workers) as pool:
            counts = pool.map(_render_range, jobs)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(f"file '{j[3].replace(os.sep, '/')}'\n")
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-movflags", "+faststart", tl.output], check=True)
    for j in jobs:
        os.remove(j[3])
    os.remove(lst)
    os.rmdir(tmp)
    return sum(counts)


def preview(tl, times, out_dir, out_time=False):
    os.makedirs(out_dir, exist_ok=True)
    rd = Reader(tl.src, tl.info["frames"])
    files = []
    for x in times:
        t = x if out_time else tl.out(x)
        ts = tl.remap.src(t)
        rd.pos = -1  # 미리보기는 임의 접근
        fr = source_frame(rd, tl, t)
        if fr is None:
            print(f"  {x}s: 프레임 없음")
            continue
        p = os.path.join(out_dir, f"prev_{x:06.2f}.jpg")
        img = render.render_frame(fr, t)
        cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        files.append((p, f"src {ts:.2f}s · out {t:.2f}s"))
    sheets = make_sheets(files, out_dir)
    print("preview:", *sheets, sep="\n  ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("timeline")
    ap.add_argument("--preview", help="원본 시각(초), 쉼표 구분")
    ap.add_argument("--preview-out", help="출력 시각(초), 쉼표 구분")
    ap.add_argument("--voice", choices=["none", "edge", "sapi"], default=None, help="성우 내레이션 (기본: VOICE['enabled'] 이면 VOICE['provider'], 아니면 none)")
    ap.add_argument("--voice-name", help="예: ko-KR-InJoonNeural, 'Microsoft Heami Desktop'")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 3)))
    args = ap.parse_args()

    tl = tlmod.load(args.timeline)
    render.setup(tl)
    print(f"[src] {tl.info['w']}x{tl.info['h']} {tl.fps_src:.2f}fps {tl.info['duration']:.2f}s · profile={tl.profile}"
          f" → {tl.output_size[0]}x{tl.output_size[1]} {tl.fps:g}fps, 출력 {tl.duration:.2f}s")
    if args.preview or args.preview_out:
        vals = args.preview or args.preview_out
        preview(tl, [float(x) for x in vals.split(",")], os.path.join(tl.build_dir, "preview"), bool(args.preview_out))
        return
    vp = args.voice or (tl.voice["provider"] if tl.voice.get("enabled") else "none")
    audio = build_audio(tl, vp, args.voice_name, args.no_music)
    print("[audio]", audio)
    if args.audio_only:
        return
    n = render_video(tl, audio, args.workers)
    srt = os.path.splitext(tl.output)[0] + ".srt"
    write_srt(tl, srt)
    info = tlmod.probe(tl.output)
    size_mb = os.path.getsize(tl.output) / 1e6
    print(f"[done] {tl.output}  {n} frames, {info['duration']:.2f}s (expected {tl.duration:.2f}s), {size_mb:.1f} MB")
    if abs(info["duration"] - tl.duration) > 0.2:
        print("  ! 출력 길이가 예상과 다릅니다 — 로그를 확인하세요.")
    print("[srt]", srt)


if __name__ == "__main__":
    main()
