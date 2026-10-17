"""영상 분석: 메타데이터, 영상 유형 추정, 화면 변화·장면 전환·소리 피크·HUD 게이지(HP 등) 이벤트, 검토용 시트와 그래프.

  python analyze.py VIDEO --out build/analysis                       # 유형 자동 추정 (auto)
  python analyze.py VIDEO --out build/analysis --mode game \\
         --bar player:335,980,628,990 --bar boss:1013,909,1595,917   # 게이지 추적 (원본 픽셀 x0,y0,x1,y1)

결과
  meta.json      해상도·fps·길이·오디오 레벨·유형 추정
  events.json    이벤트 [{t, end, kind, ...}]
                 screen : switch(클릭·탭 전환 후보) / big-change / scroll
                 공통   : cut(장면 전환) / flash(번쩍임) / loud(소리 피크) / motion(움직임 피크)
                 --bar  : bar-drop(게이지 감소: 피격) / bar-big-drop / bar-low(위험) / bar-empty(사망) / bar-rise(회복)
  curves.json    10Hz 곡선 (motion, audio_db, brightness, red, bars)
  graph.png      곡선 그래프 + 이벤트 마커 (Read 로 확인)
  static.png     거의 변하지 않는 영역(HUD·UI) 표시
  bar_<이름>.png 게이지 카이모그래프 (세로=시간) — 피격·회복 시점을 눈으로 확인
  sheets/*.jpg   이벤트 전후 + 균등 샘플 프레임 2x2 시트
  게이지 옵션: --bar 이름:x0,y0,x1,y1[:light|any]  light(기본)=밝고 채도 낮은 칸(흰 게이지), any=밝은 칸 전부(색 게이지)
"""
import argparse
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gfx import FONT_B, font  # noqa: E402
from sheet import make_sheets  # noqa: E402

SR_A = 16000


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def audio_env(path, hop=0.05):
    r = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR_A), "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, "<f4")
    if x.size == 0:
        return None
    h = int(SR_A * hop)
    n = len(x) // h
    rms = np.sqrt(np.mean(x[: n * h].reshape(n, h) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def parse_bar(s):
    name, _, rest = s.partition(":")
    parts = rest.split(":")
    box = [int(v) for v in parts[0].split(",")]
    return name, box, (parts[1] if len(parts) > 1 else "light")


def bar_fill(frame, box, kind):
    x0, y0, x1, y1 = box
    strip = frame[y0:y1 + 1, x0:x1 + 1]
    if strip.size == 0:
        return np.nan
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.float32) / 255
    s = hsv[..., 1].astype(np.float32) / 255
    # light: 흰 게이지 (피격 순간 붉게 번쩍여도 남은 칸은 채도 0.6 미만), any: 밝은 칸 전부
    filled = (v > 0.55) & (s < 0.6) if kind == "light" else (v > 0.45)
    col = np.median(filled.astype(np.float32), axis=0) > 0.5
    return float(col.mean())


def kymograph(path, rows, dur):
    """게이지 줄 픽셀을 시간축으로 쌓은 이미지 (세로=시간, 5초 눈금) — 피격·회복·번쩍임이 한눈에 보인다."""
    img = np.array(rows)
    img = cv2.resize(img, (max(360, img.shape[1]), img.shape[0]), interpolation=cv2.INTER_NEAREST)
    img = cv2.copyMakeBorder(img, 0, 0, 44, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20))
    per_s = img.shape[0] / dur
    for s in range(0, int(dur) + 1, 5):
        y = int(s * per_s)
        cv2.line(img, (0, y), (40, y), (0, 255, 255), 1)
        cv2.putText(img, str(s), (2, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    cv2.imwrite(path, img)


def smooth(x, k):
    from scipy.ndimage import median_filter
    return median_filter(x, size=k, mode="nearest")


def bar_events(name, t, f, fps):
    ev = []
    fs = smooth(f, max(3, int(fps * 0.3) | 1))  # 0.1초 번쩍임 무시
    i, n = 0, len(fs)
    win = int(fps * 0.6)
    while i < n - 1:
        j = min(n - 1, i + win)
        drop = fs[i] - fs[i:j + 1].min()
        if drop > 0.03:
            k = i + int(np.argmin(fs[i:j + 1]))
            # 낙폭이 끝날 때까지 연장
            while k + 1 < n and fs[k + 1] < fs[k] - 0.002:
                k += 1
            amt = fs[i] - fs[k]
            kind = "bar-big-drop" if amt >= 0.2 else "bar-drop"
            ev.append(dict(t=round(t[i], 2), end=round(t[k], 2), kind=kind, bar=name, amount=round(float(amt), 3),
                           after=round(float(fs[k]), 3)))
            if fs[k] < 0.25 and fs[i] >= 0.25:
                ev.append(dict(t=round(t[k], 2), kind="bar-low", bar=name, after=round(float(fs[k]), 3)))
            i = k + 1
            continue
        rise = fs[i:j + 1].max() - fs[i]
        if rise > 0.08:
            k = i + int(np.argmax(fs[i:j + 1]))
            ev.append(dict(t=round(t[i], 2), end=round(t[k], 2), kind="bar-rise", bar=name, amount=round(float(rise), 3)))
            i = k + 1
            continue
        i += max(1, win // 4)
    empty = fs < 0.02
    for k in range(1, n):
        if empty[k] and not empty[k - 1] and empty[k:k + int(fps * 0.5)].all() and fs[:k].max() > 0.2:
            ev.append(dict(t=round(t[k], 2), kind="bar-empty", bar=name))
    return ev


def peaks(x, t, thr, min_gap):
    out = []
    for i in range(1, len(x) - 1):
        if x[i] >= thr and x[i] >= x[i - 1] and x[i] >= x[i + 1]:
            if out and t[i] - out[-1][0] < min_gap:
                if x[i] > out[-1][1]:
                    out[-1] = (t[i], x[i])
                continue
            out.append((t[i], x[i]))
    return out


def graph(path, dur, curves, events, bars):
    rows = [("motion", (90, 200, 255)), ("audio_db", (255, 200, 80)), ("red", (255, 90, 90))] + [(f"bar:{b}", (120, 255, 150)) for b in bars]
    Wg, rh, pad = 1900, 120, 60
    img = Image.new("RGB", (Wg + pad, len(rows) * (rh + 26) + 60), (18, 20, 28))
    d = ImageDraw.Draw(img)
    f = font(FONT_B, 18)
    X = lambda s: pad + s / dur * (Wg - 10)
    colors = {"cut": (255, 255, 255), "bar-big-drop": (255, 60, 60), "bar-drop": (255, 150, 60), "bar-empty": (255, 0, 200),
              "bar-low": (255, 0, 120), "loud": (255, 220, 80), "flash": (200, 200, 255), "bar-rise": (80, 255, 120)}
    for r, (key, col) in enumerate(rows):
        y0 = 40 + r * (rh + 26)
        d.text((4, y0 - 22), key, font=f, fill=col)
        d.rectangle([pad, y0, Wg + pad - 10, y0 + rh], outline=(60, 64, 80))
        if key.startswith("bar:"):
            v = np.array(curves["bars"][key[4:]], float)
            lo, hi = 0, 1
        else:
            v = np.array(curves[key], float)
            lo, hi = (np.nanpercentile(v, 2), np.nanpercentile(v, 99.5)) if key != "red" else (0, max(0.05, np.nanmax(v)))
        tt = np.array(curves["t"])
        pts = [(X(a), y0 + rh - (min(max((b - lo) / (hi - lo + 1e-9), 0), 1)) * rh) for a, b in zip(tt, v) if not np.isnan(b)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2)
        for e in events:
            if e["kind"] in colors and (not key.startswith("bar:") or e.get("bar") in (None, key[4:])):
                d.line([X(e["t"]), y0, X(e["t"]), y0 + rh], fill=colors[e["kind"]], width=1)
    for s in range(0, int(dur) + 1, 5):
        d.text((X(s) - 8, 8), str(s), font=f, fill=(200, 200, 200))
        d.line([X(s), 30, X(s), img.height - 10], fill=(40, 44, 58))
    img.save(path)


def guess_type(motion, static_frac, audio_db, w, h):
    med = float(np.median(motion))
    reasons = [f"움직임 중앙값 {med:.4f}", f"정지 영역 {static_frac:.0%}"]
    if med < 0.004 and static_frac > 0.5:
        return "screen", reasons + ["대부분 정지 + 부분 변화 → 화면녹화"]
    if 0.005 < static_frac < 0.35 and med > 0.008:
        return "game", reasons + ["대부분 움직이는데 일부 영역(HUD)이 고정 → 게임 플레이 가능성"]
    return "video", reasons + ["일반 영상 (vlog/anim 은 시트를 보고 판단)"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="auto", choices=["auto", "screen", "game", "vlog", "anim"])
    ap.add_argument("--bar", action="append", default=[], help="이름:x0,y0,x1,y1[:light|any]")
    ap.add_argument("--every", type=float, default=0, help="균등 샘플 간격(초). 기본: screen 4, 그 외 2")
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "frames"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "sheets"), exist_ok=True)
    bars = [parse_bar(b) for b in args.bar]

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = int(cap.get(3)), int(cap.get(4))
    prev, prev_hist, i = None, None, 0
    motion, cutd, bright, red, diffs = [], [], [], [], []
    bar_v = {b[0]: [] for b in bars}
    kymo = {b[0]: [] for b in bars}
    static_acc = None
    frames = {}
    while True:
        ok, f = cap.read()
        if not ok:
            break
        sm = cv2.resize(f, (320, max(2, int(320 * h / w))), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 4], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev is not None:
            d = np.abs(g - prev)
            motion.append(float(d.mean() / 255))
            diffs.append((i, float((d > 25).mean())))
            cutd.append(float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)))
            ch = (d > 12).astype(np.float32)
            static_acc = ch if static_acc is None else static_acc + ch
        else:
            motion.append(0.0)
            cutd.append(0.0)
        bright.append(float(g.mean() / 255))
        b_, g_, r_ = [sm[..., k].astype(np.int16) for k in range(3)]
        red.append(float(((r_ > g_ + 60) & (r_ > b_ + 50)).mean()))
        for name, box, kind in bars:
            bar_v[name].append(bar_fill(f, box, kind))
            if i % max(1, int(round(fps / 20))) == 0:
                x0, y0, x1, y1 = box
                pad = max(20, (x1 - x0) // 8)
                kymo[name].append(f[(y0 + y1) // 2, max(0, x0 - pad):x1 + pad].copy())
        if i % max(1, int(round(fps / 4))) == 0:
            frames[i] = cv2.resize(f, (960, int(960 * h / w)))
        prev, prev_hist = g, hist
        i += 1
    n = i
    dur = n / fps
    t = np.arange(n) / fps
    motion, cutd, bright, red = map(np.array, (motion, cutd, bright, red))
    static = (static_acc / max(1, n - 1)) < 0.03 if static_acc is not None else np.zeros((2, 2), bool)
    static_frac = float(static.mean())
    adb = audio_env(args.video)
    mode = args.mode
    gtype, reasons = guess_type(motion, static_frac, adb, w, h)
    if mode == "auto":
        mode = gtype if gtype != "video" else "vlog"
    events = []

    # 공통: 장면 전환 / 번쩍임 / 소리 피크 / 움직임 피크
    for k in range(1, n):
        if cutd[k] > 0.45 and motion[k] > 0.06 and (not events or t[k] - events[-1]["t"] > 0.4):
            events.append(dict(t=round(t[k], 2), kind="cut", score=round(float(cutd[k]), 2)))
    for k in range(2, n):
        if bright[k] - bright[k - 2] > 0.12:
            if not any(e["kind"] == "flash" and t[k] - e["t"] < 0.5 for e in events):
                events.append(dict(t=round(t[k], 2), kind="flash", jump=round(float(bright[k] - bright[k - 2]), 3)))
    if adb is not None:
        ta = np.arange(len(adb)) * 0.05
        from scipy.ndimage import median_filter
        base = median_filter(adb, size=21, mode="nearest")
        on = adb - base
        for tt, v in peaks(on, ta, 7.0, 0.3):
            k = int(round(tt / 0.05))
            if adb[k] > -32:
                events.append(dict(t=round(float(tt), 2), kind="loud", db=round(float(adb[k]), 1), rise=round(float(v), 1)))
    mot_s = np.convolve(motion, np.ones(int(fps * 0.3)) / int(fps * 0.3), mode="same")
    thr = np.percentile(mot_s, 97)
    for tt, v in peaks(mot_s, t, thr, 2.0):
        events.append(dict(t=round(float(tt), 2), kind="motion", level=round(float(v), 3)))
    for name, box, kind in bars:
        events += bar_events(name, t, np.array(bar_v[name]), fps)

    # 화면녹화: 기존 클릭·전환 후보 이벤트
    if mode == "screen":
        cur, groups = None, []
        for k, c in diffs:
            if c <= 0.02:
                continue
            if cur and k - cur["k1"] <= fps * 0.25:
                cur["k1"], cur["peak"] = k, max(cur["peak"], c)
            else:
                cur = dict(k0=k, k1=k, peak=c)
                groups.append(cur)
        for e in groups:
            s, e_ = e["k0"] / fps, e["k1"] / fps
            span = e_ - s
            kind = "big-change" if e["peak"] > 0.35 else "switch" if span <= 0.25 else "scroll" if span >= 0.4 else "change"
            events.append(dict(t=round(s, 2), end=round(e_, 2), kind=kind, peak=round(e["peak"], 3)))
    events.sort(key=lambda e: e["t"])

    meta = dict(video=os.path.abspath(args.video), w=w, h=h, fps=fps, frames=n, duration=round(dur, 2),
                audio_mean_db=None if adb is None else round(float(np.mean(adb)), 1), mode=mode, guess=gtype,
                guess_reasons=reasons, static_fraction=round(static_frac, 3))
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(events, open(os.path.join(args.out, "events.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    step = max(1, int(fps / 10))
    curves = dict(t=[round(x, 2) for x in t[::step]], motion=motion[::step].round(4).tolist(),
                  brightness=bright[::step].round(3).tolist(), red=red[::step].round(4).tolist(),
                  audio_db=[] if adb is None else np.interp(t[::step], np.arange(len(adb)) * 0.05, adb).round(1).tolist(),
                  bars={k: np.array(v)[::step].round(3).tolist() for k, v in bar_v.items()})
    json.dump(curves, open(os.path.join(args.out, "curves.json"), "w"))
    if curves["audio_db"]:
        graph(os.path.join(args.out, "graph.png"), dur, curves, events, [b[0] for b in bars])
    for name, rows in kymo.items():
        if rows:
            kymograph(os.path.join(args.out, f"bar_{name}.png"), rows, dur)
    st = (static.astype(np.uint8) * 255)
    any_frame = frames[min(frames)] if frames else None
    if any_frame is not None:
        base_img = cv2.resize(any_frame, (st.shape[1], st.shape[0]))
        ov = base_img.copy()
        ov[st > 0] = (0.4 * ov[st > 0] + 0.6 * np.array([0, 255, 255])).astype(np.uint8)
        cv2.imwrite(os.path.join(args.out, "static.png"), cv2.resize(ov, (960, int(960 * h / w)), interpolation=cv2.INTER_NEAREST))

    # 검토 시트: 주요 이벤트 전후 + 균등 샘플
    every = args.every or (4.0 if mode == "screen" else 2.0)
    times = set()
    key_kinds = {"cut", "bar-big-drop", "bar-drop", "bar-empty", "bar-low", "switch", "big-change", "flash"}
    for e in events:
        if e["kind"] in key_kinds:
            times.add(max(0, e["t"] - 0.3))
            times.add(min(dur - 0.05, e.get("end", e["t"]) + 0.4))
    x = 0.0
    while x < dur:
        times.add(x)
        x += every
    picked = []
    for x in sorted(times):
        if not picked or x - picked[-1] >= 0.4:
            picked.append(x)
    files = []
    keys = np.array(sorted(frames))
    for x in picked:
        k = int(keys[np.abs(keys - x * fps).argmin()])
        p = os.path.join(args.out, "frames", f"f_{k / fps:06.2f}.jpg")
        cv2.imwrite(p, frames[k], [cv2.IMWRITE_JPEG_QUALITY, 85])
        files.append((p, f"{k / fps:.2f}s"))
    sheets = make_sheets(files, os.path.join(args.out, "sheets"))

    print(f"{w}x{h} {fps:.2f}fps {dur:.2f}s  audio mean {meta['audio_mean_db']} dB")
    print(f"유형 추정: {gtype} ({'; '.join(reasons)}) → mode={mode}")
    shown = [e for e in events if e["kind"] != "motion"] if len(events) > 60 else events
    print(f"{len(events)} events (motion 피크 {sum(e['kind'] == 'motion' for e in events)}개는 events.json 참고):")
    for e in shown:
        extra = " ".join(f"{k}={v}" for k, v in e.items() if k not in ("t", "kind"))
        print(f"  {e['t']:7.2f}s  {e['kind']:<13} {extra}")
    print(f"{len(sheets)} sheets → {os.path.join(args.out, 'sheets')}  ·  graph.png · static.png")


if __name__ == "__main__":
    main()
