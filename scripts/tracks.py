"""움직이는 대상 추적: 키프레임 보간 + (선택) OpenCV 자동 추적.

timeline.py
  TRACKS = {
      "boss":   dict(keys=[(16.0, (1240, 400, 90, 160)), (20.0, (1250, 380, 120, 200))]),   # (원본 시각, (x, y, w, h))
      "player": dict(keys=[...], auto=True),   # 키 사이를 OpenCV 추적기로 메우고, 다음 키에서 오차를 보정
      "cake":   dict(keys=[(0.5, (1140, 500, 350, 420))], auto="match", until=17.0),   # 템플릿 매칭 (형태 고정 물체)
      "candles": dict(follow="cake", offset=(0, -110), size=(190, 190)),               # 다른 트랙에 붙은 대상
  }
좌표는 원본 영상 픽셀. 키 사이는 Catmull-Rom 곡선으로 부드럽게 잇는다.
첫 키 이전·마지막 키 이후에는 가장 가까운 키 위치를 유지한다.

다른 항목에서 "@boss" 로 대상을 가리킨다.
  "@boss"        상자 중심
  "@boss:top"    상자 위쪽 가운데 (머리 위 말풍선)       :bottom / :left / :right 도 가능

검증 시트:  python tracks.py TIMELINE.py [--every 0.5]   → build/tracks/<이름>.jpg
"""
import hashlib
import json
import os
import sys

import cv2
import numpy as np


def _catmull(p0, p1, p2, p3, u):
    u2, u3 = u * u, u * u * u
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)


class Track:
    """시각(원본) → (cx, cy, w, h) 원본 픽셀."""

    def __init__(self, name, keys, samples=None):
        self.name = name
        ks = sorted(keys, key=lambda k: k[0])
        self.kt = np.array([k[0] for k in ks], float)
        self.kv = np.array([[k[1][0] + k[1][2] / 2, k[1][1] + k[1][3] / 2, k[1][2], k[1][3]] for k in ks], float)
        self.samples = samples  # 자동 추적 결과 (t 배열, v 배열) — 있으면 우선

    def at(self, t):
        if self.samples is not None:
            st, sv = self.samples
            if st[0] <= t <= st[-1]:
                return np.array([np.interp(t, st, sv[:, k]) for k in range(4)])
        kt, kv = self.kt, self.kv
        if len(kt) == 1 or t <= kt[0]:
            return kv[0].copy()
        if t >= kt[-1]:
            return kv[-1].copy()
        i = int(np.searchsorted(kt, t)) - 1
        u = (t - kt[i]) / (kt[i + 1] - kt[i])
        p0 = kv[max(0, i - 1)]
        p3 = kv[min(len(kv) - 1, i + 2)]
        v = _catmull(p0, kv[i], kv[i + 1], p3, u)
        v[2:] = np.maximum(v[2:], 2)
        return v

    def point(self, t, anchor=""):
        cx, cy, w, h = self.at(t)
        return {"": (cx, cy), "top": (cx, cy - h / 2), "bottom": (cx, cy + h / 2),
                "left": (cx - w / 2, cy), "right": (cx + w / 2, cy)}[anchor]

    def rect(self, t):
        cx, cy, w, h = self.at(t)
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


class FollowTrack(Track):
    """다른 트랙에 붙은 대상: 부모 중심 + offset, 부모 크기 변화에 비례해 offset·size 도 커진다."""

    def __init__(self, name, parent, offset, size):
        self.name, self.parent = name, parent
        self.offset, self.size = np.array(offset, float), np.array(size, float)
        self.w0 = parent.at(parent.kt[0])[2]
        self.kt = parent.kt
        self.samples = None

    def at(self, t):
        cx, cy, w, h = self.parent.at(t)
        k = w / self.w0
        return np.array([cx + self.offset[0] * k, cy + self.offset[1] * k, self.size[0] * k, self.size[1] * k])


# ---------------------------------------------------------------- 자동 추적 (키 사이를 MIL 추적기로 메우고 드리프트 보정)
def _make_tracker():
    for name in ("TrackerCSRT_create", "TrackerKCF_create", "TrackerMIL_create"):
        if hasattr(cv2, name):
            return getattr(cv2, name)()
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, name):
            return getattr(cv2.legacy, name)()
    return None


class _Matcher:
    """템플릿 매칭 추적 — 케이크·간판·휴대폰처럼 모양이 변하지 않는 물체에 강하다 (크기 변화 ±6%/프레임 탐색)."""

    def __init__(self, small, box):
        x, y, w, h = [int(v) for v in box]
        self.tpl = small[y:y + h, x:x + w].copy()
        self.box = [float(x), float(y), float(w), float(h)]
        self.s = 1.0
        self.score = 1.0

    def update(self, small):
        H, W = small.shape[:2]
        x, y, w, h = self.box
        best = (-1, None)
        for ds in (0.96, 1.0, 1.04):
            s = self.s * ds
            tw, th = int(self.tpl.shape[1] * s), int(self.tpl.shape[0] * s)
            if tw < 8 or th < 8:
                continue
            tpl = cv2.resize(self.tpl, (tw, th), interpolation=cv2.INTER_AREA)
            mx, my = int(w * 0.6) + 8, int(h * 0.6) + 8
            cx, cy = x + w / 2, y + h / 2
            x0, y0 = int(max(0, cx - tw / 2 - mx)), int(max(0, cy - th / 2 - my))
            x1, y1 = int(min(W, cx + tw / 2 + mx)), int(min(H, cy + th / 2 + my))
            if x1 - x0 <= tw or y1 - y0 <= th:
                continue
            r = cv2.matchTemplate(small[y0:y1, x0:x1], tpl, cv2.TM_CCOEFF_NORMED)
            _, v, _, loc = cv2.minMaxLoc(r)
            if v > best[0]:
                best = (v, (x0 + loc[0], y0 + loc[1], tw, th, s))
        self.score = best[0]
        if best[1] is None or best[0] < 0.35:
            return False, self.box
        bx, by, bw, bh, s = best[1]
        self.box, self.s = [float(bx), float(by), float(bw), float(bh)], s
        return True, self.box


def auto_track(src, fps, keys, scale=0.5, step=2, method="mil", until=None):
    """keys: [(t, (x,y,w,h))] → (t 배열, [cx,cy,w,h] 배열).
    method: "mil"(OpenCV 추적기, 사람·동물) | "match"(템플릿 매칭, 형태가 고정된 물체).
    각 키에서 다시 시작하고 다음 키와의 오차를 구간에 나눠 보정한다. until 이 있으면 마지막 키 이후 그 시각까지 계속 추적."""
    ks = sorted(keys, key=lambda k: k[0])
    segs = list(zip(ks[:-1], ks[1:]))
    if until and until > ks[-1][0]:
        segs.append((ks[-1], (until, None)))
    cap = cv2.VideoCapture(src)
    out_t, out_v = [], []
    for (ta, ra), (tb, rb) in segs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(ta * fps))
        ok, fr = cap.read()
        if not ok:
            return None
        small = cv2.resize(fr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        sbox = tuple(v * scale for v in ra)
        if method == "match":
            tr = _Matcher(small, sbox)
        else:
            tr = _make_tracker()
            if tr is None:
                return None
            tr.init(small, tuple(int(v) for v in sbox))
        seg_t, seg_v = [ta], [[ra[0] + ra[2] / 2, ra[1] + ra[3] / 2, ra[2], ra[3]]]
        last = seg_v[0]
        n = int(round((tb - ta) * fps))
        rb_ = rb or ra
        for k in range(1, n + 1):
            ok, fr = cap.read()
            if not ok:
                break
            if k % step:
                continue
            small = cv2.resize(fr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            good, bb = tr.update(small)
            if good:
                x, y, w, h = [v / scale for v in bb]
                if method == "match":
                    last = [x + w / 2, y + h / 2, w, h]
                else:
                    last = [x + w / 2, y + h / 2, ra[2] + (rb_[2] - ra[2]) * k / n, ra[3] + (rb_[3] - ra[3]) * k / n]
            seg_t.append(ta + k / fps)
            seg_v.append(list(last))
        seg_v = np.array(seg_v)
        seg_t = np.array(seg_t)
        if rb is not None:  # 다음 키와의 오차를 구간 전체에 선형으로 나눠 보정
            target = np.array([rb[0] + rb[2] / 2, rb[1] + rb[3] / 2, rb[2], rb[3]])
            err = target - seg_v[-1]
            w = ((seg_t - ta) / max(1e-6, tb - ta))[:, None]
            seg_v = seg_v + err * w
        out_t.extend(seg_t.tolist())
        out_v.extend(seg_v.tolist())
    cap.release()
    return np.array(out_t), np.array(out_v)


def build_tracks(spec, src, fps, cache_dir):
    tracks = {}
    spec = spec or {}
    for name, cfg in spec.items():
        if "follow" in cfg:
            continue
        keys = cfg["keys"]
        samples = None
        until = cfg.get("until")
        if cfg.get("auto") and (len(keys) >= 2 or until):
            method = cfg["auto"] if isinstance(cfg["auto"], str) else "mil"
            h = hashlib.sha1(json.dumps([src, keys, method, until], default=str).encode()).hexdigest()[:12]
            path = os.path.join(cache_dir, f"{name}_{h}.npz")
            if os.path.exists(path):
                d = np.load(path)
                samples = (d["t"], d["v"])
            else:
                res = auto_track(src, fps, keys, method=method, until=until)
                if res is not None:
                    os.makedirs(cache_dir, exist_ok=True)
                    np.savez(path, t=res[0], v=res[1])
                    samples = res
                else:
                    print(f"  ! 추적기를 쓸 수 없어 '{name}' 은 키프레임 보간만 사용합니다")
        tracks[name] = Track(name, keys, samples)
    for name, cfg in spec.items():
        if "follow" in cfg:
            tracks[name] = FollowTrack(name, tracks[cfg["follow"]], cfg.get("offset", (0, 0)), cfg.get("size", (80, 80)))
    return tracks


def main():
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import tl as tlmod
    from sheet import make_sheets

    ap = argparse.ArgumentParser(description="TRACKS 검증 시트")
    ap.add_argument("timeline")
    ap.add_argument("--every", type=float, default=0.5)
    ap.add_argument("--only")
    args = ap.parse_args()
    tl = tlmod.load(args.timeline)
    out_dir = os.path.join(tl.build_dir, "tracks")
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(tl.src)
    for name, tr in tl.tracks.items():
        if args.only and name != args.only:
            continue
        base = getattr(tr, "parent", tr)
        t0, t1 = (base.samples[0][0], base.samples[0][-1]) if base.samples is not None else (tr.kt[0], tr.kt[-1])
        files = []
        for t in np.arange(t0, t1 + 1e-6, args.every):
            cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * tl.fps))
            ok, fr = cap.read()
            if not ok:
                continue
            x0, y0, x1, y1 = [int(v) for v in tr.rect(t)]
            cv2.rectangle(fr, (x0, y0), (x1, y1), (0, 220, 255), 4)
            is_key = np.min(np.abs(tr.kt - t)) < 1e-3
            cv2.putText(fr, f"{name} {'KEY' if is_key else ''}", (x0, max(30, y0 - 12)), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                        (0, 220, 255), 3)
            p = os.path.join(out_dir, f"{name}_{t:06.2f}.jpg")
            cv2.imwrite(p, cv2.resize(fr, (960, int(960 * fr.shape[0] / fr.shape[1]))))
            files.append((p, f"{t:.2f}s"))
        sheets = make_sheets(files, out_dir, prefix=f"{name}_sheet")
        print(name, *sheets, sep="\n  ")


if __name__ == "__main__":
    main()
