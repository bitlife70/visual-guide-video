"""타임라인 로더: 사용자 timeline.py 를 읽어 프로필 기본값을 채우고, 원본 좌표·시각을 캔버스 좌표·출력 시각으로 변환한다.

- 좌표: 원본 영상 픽셀. 원본 해상도·비율이 달라도 1920x1080 디자인 캔버스에 레터박스로 맞춘다.
- 시각: 원본 영상 시각. TRIM·SPEED·FREEZE 를 반영해 출력 시각으로 바꾼다 (remap.py).
- 대상: (x, y) 고정 좌표 또는 "@트랙이름[:top|bottom|left|right]" (tracks.py).
"""
import importlib.util
import os
import types

import cv2

from remap import Remap
from tracks import build_tracks

W, H = 1920, 1080

# 영상 유형별 기본값 — timeline.py 의 값이 항상 우선한다
PROFILES = {
    "screen": dict(music=dict(style="pop", volume=0.82), source_audio=dict(enabled=False, volume=1.0),
                   caption=dict(size=40, bottom=52), progress=True, grade=None, fps=None),
    "game": dict(music=dict(style="epic", volume=0.5), source_audio=dict(enabled=True, volume=0.9),
                 caption=dict(size=36, bottom=26), progress=False, grade="cinematic", fps=30),
    "vlog": dict(music=dict(style="chill", volume=0.42), source_audio=dict(enabled=True, volume=1.0),
                 caption=dict(size=38, bottom=44), progress=False, grade="warm", fps=30),
    "anim": dict(music=dict(style="cute", volume=0.55), source_audio=dict(enabled=True, volume=0.8),
                 caption=dict(size=38, bottom=44), progress=False, grade="vivid", fps=None),
}


def probe(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise FileNotFoundError(f"영상을 열 수 없습니다: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return dict(w=w, h=h, fps=fps, frames=n, duration=n / fps)


class Target:
    """고정 좌표 또는 트랙을 가리키는 대상. pt(ts)/rect(ts) 는 캔버스 좌표."""

    def __init__(self, spec, tl):
        self.tl = tl
        self.spec = spec
        self.track, self.anchor = None, ""
        if isinstance(spec, str):
            if not spec.startswith("@"):
                raise ValueError(f"대상은 (x, y) 또는 '@트랙' 이어야 합니다: {spec!r}")
            name, _, anchor = spec[1:].partition(":")
            if name not in tl.tracks:
                raise KeyError(f"TRACKS 에 '{name}' 이 없습니다")
            self.track, self.anchor = tl.tracks[name], anchor

    @property
    def dynamic(self):
        return self.track is not None

    def pt(self, ts):
        if self.track:
            return self.tl.P(self.track.point(ts, self.anchor))
        s = self.spec
        if len(s) == 4:
            return self.tl.P(((s[0] + s[2]) / 2, (s[1] + s[3]) / 2))
        return self.tl.P(s)

    def rect(self, ts):
        if self.track:
            return self.tl.R(self.track.rect(ts))
        s = self.spec
        if len(s) == 4:
            return self.tl.R(s)
        x, y = self.tl.P(s)
        return (x - 40, y - 40, x + 40, y + 40)

    def src_pt(self, ts):
        if self.track:
            return self.track.point(ts, self.anchor)
        s = self.spec
        return ((s[0] + s[2]) / 2, (s[1] + s[3]) / 2) if len(s) == 4 else tuple(s)


def _merge(base, over):
    d = dict(base)
    d.update(over or {})
    return d


def load(path):
    path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("user_timeline", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def g(k, d=None):
        return getattr(m, k, d)

    base = os.path.dirname(path)
    t = types.SimpleNamespace()
    t.module = m
    t.timeline_path = path
    t.base = base
    t.src = os.path.join(base, m.SRC)
    t.info = probe(t.src)
    t.profile = g("PROFILE", "screen")
    if t.profile not in PROFILES:
        raise ValueError(f"PROFILE 은 {list(PROFILES)} 중 하나: {t.profile!r}")
    prof = PROFILES[t.profile]

    # ---- 좌표: 원본 → 1920x1080 디자인 캔버스 (레터박스)
    sw, shh = t.info["w"], t.info["h"]
    s = min(W / sw, H / shh)
    ox, oy = (W - sw * s) / 2, (H - shh * s) / 2
    t.scale, t.offset = s, (ox, oy)
    t.content = (ox, oy, ox + sw * s, oy + shh * s)  # 캔버스에서 실제 영상이 차지하는 영역

    def P(p):
        return (p[0] * s + ox, p[1] * s + oy)

    def R(r):
        return (r[0] * s + ox, r[1] * s + oy, r[2] * s + ox, r[3] * s + oy)

    t.P, t.R = P, R
    t.fps_src = t.info["fps"]
    t.fps = float(g("FPS", prof["fps"]) or t.fps_src)
    t.output_size = tuple(g("OUTPUT_SIZE", (W, H)))
    t.quality = int(g("QUALITY", 18 if t.output_size[1] >= 1080 else 21))
    t.output = os.path.join(base, g("OUTPUT", "output/guide.mp4"))
    t.build_dir = os.path.join(base, g("BUILD_DIR", "build"))
    t.theme = g("THEME")
    t.fade_out = g("FADE_OUT", 0.55)

    # ---- 시간: 원본 → 출력
    trim = g("TRIM") or (0.0, float(g("DURATION", t.info["duration"])))
    trim = (max(0.0, float(trim[0])), min(float(trim[1]), t.info["duration"]))
    t.remap = Remap(trim[0], trim[1], g("SPEED", []) or [], g("FREEZE", []) or [])
    t.duration = t.remap.duration

    # 시각은 원본 초 또는 (원본 초, 출력 오프셋초) — 예: (49.45, 1.5) = 49.45초 정지가 시작되고 1.5초 뒤
    def O(x, side="left"):
        if isinstance(x, (tuple, list)):
            return t.remap.out(x[0], "left") + x[1]  # 오프셋은 항상 그 시각에 처음 도달한 순간 기준
        return t.remap.out(x, side)

    def span(a, b):
        return O(a, "left"), O(b, "right")

    t.out, t.span = O, span

    # ---- 트랙 / 대상
    t.tracks = build_tracks(g("TRACKS"), t.src, t.fps_src, os.path.join(t.build_dir, "tracks_cache"))

    def T(x):
        return Target(x, t)

    t.target = T

    # ---- 카메라: (t, dur, cx, cy, z) | (t, dur, "full"[, z]) | (t, dur, "fill") | (t, dur, "@트랙", z[, (dx, dy)])
    shots = []
    for sh in g("SHOTS") or [(trim[0], 0, "full")]:
        a, b = span(sh[0], sh[0] + sh[1])
        dur = max(0.0, b - a)
        if sh[2] == "full":
            shots.append(dict(t=a, dur=dur, target=None, c=(W / 2, H / 2), z=sh[3] if len(sh) > 3 else 1.0))
        elif sh[2] == "fill":
            cw, ch = t.content[2] - t.content[0], t.content[3] - t.content[1]
            shots.append(dict(t=a, dur=dur, target=None, c=(W / 2, H / 2), z=max(W / cw, H / ch) * (sh[3] if len(sh) > 3 else 1.0)))
        elif isinstance(sh[2], str):
            off = sh[4] if len(sh) > 4 else (0, 0)
            shots.append(dict(t=a, dur=dur, target=T(sh[2]), c=None, z=sh[3], off=(off[0] * s, off[1] * s)))
        else:
            shots.append(dict(t=a, dur=dur, target=None, c=P(sh[2:4]), z=sh[4]))
    if shots[0]["t"] > 0 or shots[0]["dur"] > 0:
        shots.insert(0, dict(t=0, dur=0, target=None, c=(W / 2, H / 2), z=1.0))
    t.shots = shots

    # ---- 화면녹화형 요소
    t.clicks = [(O(c[0]), P(c[1]), c[2]) for c in g("CLICKS", [])]
    t.links = [(*span(a, b), P(src), R(rect), label) for a, b, src, rect, label in g("LINKS", [])]
    t.highlights = [(*span(h[0], h[1]), T(h[2]), h[3], h[4] if len(h) > 4 else "accent", *(h[5:])) for h in g("HIGHLIGHTS", [])]
    t.cards = [(*span(c[0], c[1]), *c[2:]) + (("실행 중",) if len(c) == 5 else ()) for c in g("CARDS", [])]
    t.card_pos = g("CARD_POS", (W - 36, 560))
    t.subtitles = [(*span(a, b), text) for a, b, text in g("SUBTITLES", [])]
    t.caption = _merge(prof["caption"], g("CAPTION"))
    t.progress = g("PROGRESS", prof["progress"])
    flow = g("FLOW")
    if flow:
        flow = dict(flow)
        flow["range"] = span(*flow["range"])
        flow["items"] = [(O(it[0]), *it[1:]) for it in flow["items"]]
    t.flow = flow
    hud = g("HUD")
    if hud:
        hud = dict(hud)
        hud["range"] = span(*hud["range"])
        hud["active"] = [(O(a), v) for a, v in hud.get("active", [(trim[0], 0)])]
        hud["steps"] = [(O(a), v) for a, v in hud.get("steps", [])]
    t.hud = hud
    title = g("TITLE")
    if title:
        title = dict(title)
        title["range"] = span(*title["range"])
    t.title = title
    outro = g("OUTRO")
    if outro:
        outro = dict(outro)
        outro["start"] = O(outro["start"])
    t.outro = outro

    # ---- 범용 연출 (fx.py)
    t.speed_labels = [(*span(sp[0], sp[1]), sp[2], sp[3]) for sp in g("SPEED", []) or [] if len(sp) > 3]
    t.freezes = [(O(f[0], "left"), O(f[0], "right"), f[2] if len(f) > 2 else None, f[3] if len(f) > 3 else {})
                 for f in g("FREEZE", []) or []]
    t.speed_blend = g("SPEED_BLEND", True)  # 빨리감기(2배 이상) 구간에서 프레임을 섞어 모션블러
    t.particles = [(*span(p[0], p[1]), p[2], p[3] if len(p) > 3 else {}) for p in g("PARTICLES", [])]
    t.photos = [(*span(p[0], p[1]), p[2], p[3], p[4] if len(p) > 4 else "", p[5] if len(p) > 5 else {})
                for p in g("PHOTOS", [])]
    t.shakes = [(O(sh[0]), sh[1], sh[2] if len(sh) > 2 else 0.45) for sh in g("SHAKE", [])]
    t.flashes = [(O(f[0]), f[1], f[2] if len(f) > 2 else 0.6, f[3] if len(f) > 3 else 0.35) for f in g("FLASH", [])]
    t.impacts = [(O(i[0]), i[1] if len(i) > 1 else "hit") for i in g("IMPACTS", [])]
    t.grade = g("GRADE", prof["grade"])
    t.grades = [(*span(a, b), p) for a, b, p in g("GRADES", [])]
    t.magnify = [(*span(mg[0], mg[1]), T(mg[2]), mg[3], mg[4] if len(mg) > 4 else "", mg[5] if len(mg) > 5 else {})
                 for mg in g("MAGNIFY", [])]
    t.callouts = [(*span(c[0], c[1]), T(c[2]), c[3], c[4] if len(c) > 4 else {}) for c in g("CALLOUTS", [])]
    t.pops = [(*span(p[0], p[1]), p[2] if p[2] == "center" or isinstance(p[2], dict) else T(p[2]), p[3],
               p[4] if len(p) > 4 else "impact") for p in g("POPS", [])]
    t.stickers = [(*span(st[0], st[1]), T(st[2]), st[3], st[4] if len(st) > 4 else {}) for st in g("STICKERS", [])]
    # SFX 시각: 원본 시각 t 또는 (t, 출력 오프셋초) — 예: (78.2, 0.5) = 78.2초 정지 시작 0.5초 뒤
    def sfx_t(x):
        return O(x[0]) + x[1] if isinstance(x, (tuple, list)) else O(x)

    t.sfx = [(sfx_t(x[0]), x[1], x[2] if len(x) > 2 else 1.0, x[3] if len(x) > 3 else 0.0) for x in g("SFX", [])]
    t.custom_layers = list(g("CUSTOM_LAYERS", []) or [])
    t.custom_frame_fx = list(g("CUSTOM_FRAME_FX", []) or [])
    t.custom_sfx = list(g("CUSTOM_SFX", []) or [])

    # ---- 오디오
    t.narration = [(O(n[0]), *n[1:]) for n in g("NARRATION")] if g("NARRATION") else None
    t.voice = dict(provider="edge", voice="ko-KR-SunHiNeural", rate="+0%", gain_db=0.0)
    t.voice.update(g("VOICE", {}) or {})
    t.music = dict(enabled=True, style="pop", bpm=None, transpose=0, drop=None, intro_bars=None, volume=0.82, duck=0.55,
                   end=None, start=None)
    t.music.update(prof["music"])
    t.music.update(g("MUSIC", {}) or {})
    for k in ("drop", "end", "start"):
        if t.music.get(k) is not None:
            t.music[k] = O(t.music[k])
    t.source_audio = _merge(prof["source_audio"], g("SOURCE_AUDIO"))
    t.sfx_volume = float(g("SFX_VOLUME", 1.0))
    t.master_gain_db = float(g("MASTER_GAIN_DB", 0.0))  # 최종 믹스 게인 (리미터 전). 휴대폰 영상은 +3~5 dB
    return t
