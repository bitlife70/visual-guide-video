"""그래픽 엔진: 이징, 이모지 포함 리치 텍스트 스프라이트(PIL), 안티앨리어싱 도형(OpenCV), premultiplied 합성.

모든 좌표는 디자인 캔버스 픽셀 기준 (기본 1920x1080, 세로 쇼츠는 timeline.py 의 CANVAS = (1080, 1920)).
"""
import math
import os
import re
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def canvas_from_env():
    """디자인 캔버스 크기. build.py 가 timeline.py 의 CANVAS 를 읽어 VGUIDE_CANVAS='1080x1920' 으로 넘긴다."""
    v = os.environ.get("VGUIDE_CANVAS", "")
    m = re.fullmatch(r"\s*(\d+)\s*[xX,]\s*(\d+)\s*", v)
    return (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)


W, H = canvas_from_env()


# ---------------------------------------------------------------- fonts (크로스 플랫폼)
def _find(env, candidates):
    p = os.environ.get(env)
    if p and os.path.exists(p):
        return p
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(f"폰트를 찾지 못했습니다. 환경변수 {env} 로 경로를 지정하세요. 후보: {candidates}")


FONT_B = _find("VGUIDE_FONT_BOLD", [
    "C:/Windows/Fonts/malgunbd.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
])
FONT_R = _find("VGUIDE_FONT_REGULAR", [
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
])
FONT_E = _find("VGUIDE_FONT_EMOJI", [
    "C:/Windows/Fonts/seguiemj.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
])

# ---------------------------------------------------------------- theme
ACCENT = (255, 138, 61)
CYAN = (64, 214, 255)
GREEN = (80, 224, 140)
INK = (20, 22, 30)
WHITE = (255, 255, 255)
COLORS = {"accent": ACCENT, "cyan": CYAN, "green": GREEN}


def set_theme(theme):
    """THEME = dict(accent=(r,g,b), cyan=(r,g,b), green=(r,g,b)) 로 색 교체."""
    global ACCENT, CYAN, GREEN
    if not theme:
        return
    ACCENT = tuple(theme.get("accent", ACCENT))
    CYAN = tuple(theme.get("cyan", CYAN))
    GREEN = tuple(theme.get("green", GREEN))
    COLORS.update(accent=ACCENT, cyan=CYAN, green=GREEN)


# ---------------------------------------------------------------- easing
def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_io(u):
    u = clamp01(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def ease_out(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 3


def ease_back(u, s=1.7):
    u = clamp01(u)
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


def window(t, t0, t1, fin=0.3, fout=0.25):
    """구간 [t0,t1] 의 (alpha, 등장 진행도 u_in). 구간 밖이면 None."""
    if t < t0 or t > t1:
        return None
    a = min(clamp01((t - t0) / fin) if fin else 1, clamp01((t1 - t) / fout) if fout else 1)
    return a, clamp01((t - t0) / fin) if fin else 1.0


# ---------------------------------------------------------------- text
@lru_cache(None)
def font(path, size):
    return ImageFont.truetype(path, size)


def is_emoji(ch):
    cp = ord(ch)
    return (cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or 0x2190 <= cp <= 0x21FF or 0x23E9 <= cp <= 0x23FA
            or cp in (0x231A, 0x231B, 0x2328, 0x23CF, 0x2B50, 0x2B06, 0x2B07, 0x2B55, 0x2B1B, 0x2B1C))


def _runs(text):
    out = []
    for ch in text:
        if ch in ("\ufe0f", "\u200d"):
            continue
        e = is_emoji(ch)
        if out and out[-1][0] == e:
            out[-1][1] += ch
        else:
            out.append([e, ch])
    return out


@lru_cache(None)
def _emoji_native_size():
    """비트맵 이모지 폰트(Noto 109px, Apple 160px)는 고정 크기만 지원 → 네이티브로 그린 뒤 축소."""
    for s in (109, 160, 128, 96, 64):
        try:
            ImageFont.truetype(FONT_E, s)
            if "seguiemj" in FONT_E.lower():
                return 128
            return s
        except OSError:
            continue
    return 109


@lru_cache(None)
def emoji_img(run, size):
    ns = _emoji_native_size()
    f = ImageFont.truetype(FONT_E, ns)
    asc, desc = f.getmetrics()
    w = max(1, int(f.getlength(run)) + 4)
    im = Image.new("RGBA", (w, asc + desc + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, asc), run, font=f, anchor="ls", embedded_color=True)
    k = size * 0.92 / ns
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return im, asc * k


def parse_rich(text, base, accent):
    """'[강조]' 마크업을 (문자열, 색) 세그먼트로."""
    segs = []
    for i, part in enumerate(re.split(r"\[(.+?)\]", text)):
        if part:
            segs.append((part, accent if i % 2 else base))
    return segs


def strip_markup(text):
    return re.sub(r"\[(.+?)\]", r"\1", text)


def rich_width(segs, size, bold=True):
    w = 0
    for s, _ in segs:
        for e, r in _runs(s):
            if e:
                w += emoji_img(r, size)[0].width
            else:
                w += font(FONT_B if bold else FONT_R, size).getlength(r)
    return w


def draw_rich(d, x, baseline, segs, size, bold=True):
    """ImageDraw d 의 이미지에 리치 텍스트를 그림. 이모지는 컬러 비트맵 합성."""
    for s, col in segs:
        for e, r in _runs(s):
            if e:
                im, asc = emoji_img(r, size)
                d._image.alpha_composite(im, (int(x), int(baseline - asc)))
                x += im.width
            else:
                f = font(FONT_B if bold else FONT_R, size)
                d.text((x, baseline), r, font=f, anchor="ls", fill=col)
                x += f.getlength(r)
    return x


# ---------------------------------------------------------------- sprites
def to_premul(img):
    """PIL RGBA → premultiplied float32 RGBA (0..1)."""
    a = np.asarray(img, dtype=np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a


def with_shadow(img, radius=14, offset=(0, 8), opacity=0.55, pad=30):
    w, h = img.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    alpha = img.split()[3].point(lambda v: int(v * opacity))
    sh.paste((0, 0, 0, 255), (pad + offset[0], pad + offset[1]), alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    canvas.alpha_composite(sh)
    canvas.alpha_composite(img, (pad, pad))
    return canvas, pad


class Sprite:
    def __init__(self, img, pad=0):
        self.arr = to_premul(img)
        self.h, self.w = self.arr.shape[:2]
        self.pad = pad  # 그림자 여백 (본체 좌상단 = 스프라이트 좌상단 + pad)

    @property
    def body(self):
        return self.w - 2 * self.pad, self.h - 2 * self.pad


def _rgba(c):
    return tuple(c) if len(c) == 4 else (*c, 255)


@lru_cache(None)
def pill_sprite(text, size=34, fg=INK, bg=WHITE, accent=None, padx=24, pady=14, radius=None, border=None):
    accent = accent or ACCENT
    segs = parse_rich(text, fg, accent)
    tw = int(rich_width(segs, size)) + 2
    w, h = tw + padx * 2, int(size * 1.35) + pady * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = radius if radius is not None else h // 2
    d.rounded_rectangle([0, 0, w - 1, h - 1], r, fill=_rgba(bg), outline=border, width=2 if border else 0)
    draw_rich(d, padx, pady + int(size * 1.05), segs, size)
    img, pad = with_shadow(img)
    return Sprite(img, pad)


@lru_cache(None)
def subtitle_sprite(text, max_w=1720, size=40):
    min_size = min(28, size)
    while True:  # 길면 자동 축소
        segs = parse_rich(text, (245, 247, 252), ACCENT)
        tw = int(rich_width(segs, size)) + 2
        if tw + 88 <= max_w or size <= min_size:
            break
        size -= 2
    padx, pady = 34, 18
    w, h = tw + padx * 2 + 10, int(size * 1.35) + pady * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 18, fill=(14, 16, 24, 228), outline=(255, 255, 255, 40), width=2)
    d.rounded_rectangle([0, 0, 9, h - 1], 4, fill=ACCENT)
    draw_rich(d, padx + 10, pady + int(size * 1.05), segs, size)
    img, pad = with_shadow(img, radius=18, opacity=0.6)
    return Sprite(img, pad)


@lru_cache(None)
def card_sprite(emoji, title, lines, badge="실행 중"):
    w = 640
    th, lh = 40, 29
    h = 34 + int(th * 1.3) + 14 + len(lines) * int(lh * 1.55) + 22
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 22, fill=(16, 18, 27, 238), outline=(255, 255, 255, 46), width=2)
    d.rounded_rectangle([0, 0, 10, h - 1], 5, fill=ACCENT)
    y = 34 + int(th * 1.05)
    x = draw_rich(d, 36, y, [(emoji + " ", WHITE)], th + 6) if emoji else 36
    draw_rich(d, x, y, [(title, WHITE)], th)
    if badge:
        bw = int(rich_width([(badge, GREEN)], 22)) + 54
        bx = w - 30 - bw
        d.rounded_rectangle([bx, 26, bx + bw, 62], 18, fill=(*GREEN, 40), outline=GREEN, width=2)
        d.ellipse([bx + 14, 37, bx + 28, 51], fill=GREEN)
        draw_rich(d, bx + 38, 53, [(badge, GREEN)], 22)
    y += 22
    for ln in lines:
        y += int(lh * 1.55)
        draw_rich(d, 38, y, [("• ", ACCENT), (ln, (214, 220, 232))], lh, bold=False)
    img, pad = with_shadow(img, radius=22, opacity=0.65)
    return Sprite(img, pad)


CHIP_W = 300


@lru_cache(None)
def chip_sprite(emoji, title, sub, status):
    w, h = CHIP_W, 128
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = {"done": GREEN, "run": ACCENT, "next": (150, 156, 175)}[status]
    d.rounded_rectangle([0, 0, w - 1, h - 1], 20, fill=(16, 18, 27, 240), outline=col, width=3)
    draw_rich(d, 20, 60, [(emoji, WHITE)], 40)
    draw_rich(d, 78, 52, [(title, WHITE)], 26)
    draw_rich(d, 78, 86, [(sub, (170, 178, 196))], 20, bold=False)
    tag = [({"done": "완료", "run": "진행 중", "next": "다음"}[status], col)]
    tw = rich_width(tag, 20)
    draw_rich(d, w - 20 - tw, h - 14, tag, 20)
    d.ellipse([w - 36 - tw, h - 29, w - 26 - tw, h - 19], fill=col)
    img, pad = with_shadow(img, radius=16)
    return Sprite(img, pad)


# ---------------------------------------------------------------- canvas (premultiplied float overlay)
class Canvas:
    def __init__(self):
        self.buf = np.zeros((H, W, 4), np.float32)

    def clear(self):
        self.buf.fill(0)

    def _over(self, src, x, y, alpha=1.0):
        h, w = src.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        s = src[y0 - y:y1 - y, x0 - x:x1 - x]
        if alpha != 1.0:
            s = s * alpha
        d = self.buf[y0:y1, x0:x1]
        d *= 1.0 - s[..., 3:4]
        d += s

    def sprite(self, sp, cx, cy, alpha=1.0, scale=1.0, anchor=(0.5, 0.5)):
        """본체(그림자 제외)의 anchor 비율 지점을 (cx, cy)에 배치."""
        if alpha <= 0.003:
            return
        arr = sp.arr
        if abs(scale - 1.0) > 1e-3:
            arr = cv2.resize(arr, (max(1, int(sp.w * scale)), max(1, int(sp.h * scale))), interpolation=cv2.INTER_LINEAR)
        h, w = arr.shape[:2]
        pad = sp.pad * scale
        bw, bh = w - 2 * pad, h - 2 * pad
        ax, ay = anchor
        x = int(round(cx - ax * bw - pad))
        y = int(round(cy - ay * bh - pad))
        self._over(arr, x, y, alpha)

    def shape(self, bbox, draw_fn, alpha=1.0, glow=0):
        """bbox 영역에 cv2 도형을 AA로 그려 합성. draw_fn(img, ox, oy) — img 는 uint8 RGBA."""
        if alpha <= 0.003:
            return
        m = 8 + glow * 3
        x0, y0 = int(max(0, bbox[0] - m)), int(max(0, bbox[1] - m))
        x1, y1 = int(min(W, bbox[2] + m)), int(min(H, bbox[3] + m))
        if x1 <= x0 or y1 <= y0:
            return
        img = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        draw_fn(img, x0, y0)
        a = img.astype(np.float32) / 255.0
        if glow:
            g = cv2.GaussianBlur(a, (0, 0), glow)
            self._over(g * 0.9, x0, y0, alpha)
        self._over(a, x0, y0, alpha)

    def composite(self, frame_bgr):
        f = frame_bgr.astype(np.float32) / 255.0
        o = self.buf
        rgb = o[..., 2::-1]  # RGB → BGR
        out = f * (1.0 - o[..., 3:4]) + rgb
        return np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- shape helpers (좌표는 화면 px)
SH = 4  # cv2 subpixel shift
SC = 1 << SH


def _p(pts, ox, oy):
    return (np.asarray(pts, np.float64) - (ox, oy)) * SC


def rrect_pts(x0, y0, x1, y1, r, n=10):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rgba(c, a=255):
    return (int(c[0]), int(c[1]), int(c[2]), int(a))


def draw_rrect(cv, rect, color, thick=4, r=12, alpha=1.0, fill=None, glow=0):
    x0, y0, x1, y1 = rect
    pts = rrect_pts(x0, y0, x1, y1, r)

    def fn(img, ox, oy):
        p = _p(pts, ox, oy).astype(np.int32)
        if fill is not None:
            cv2.fillPoly(img, [p], rgba(fill[:3], fill[3]), cv2.LINE_AA, SH)
        cv2.polylines(img, [p], True, rgba(color), thick, cv2.LINE_AA, SH)

    cv.shape((x0, y0, x1, y1), fn, alpha, glow)


def draw_ring(cv, c, radius, color, thick, alpha):
    def fn(img, ox, oy):
        cv2.circle(img, (int((c[0] - ox) * SC), int((c[1] - oy) * SC)), int(radius * SC), rgba(color), max(1, int(thick)), cv2.LINE_AA, SH)

    cv.shape((c[0] - radius - thick, c[1] - radius - thick, c[0] + radius + thick, c[1] + radius + thick), fn, alpha)


def draw_dot(cv, c, radius, color, alpha=1.0, glow=0):
    def fn(img, ox, oy):
        cv2.circle(img, (int((c[0] - ox) * SC), int((c[1] - oy) * SC)), int(radius * SC), rgba(color), -1, cv2.LINE_AA, SH)

    cv.shape((c[0] - radius, c[1] - radius, c[0] + radius, c[1] + radius), fn, alpha, glow)


def bezier(p0, p1, bend=0.25, n=48):
    p0, p1 = np.array(p0, float), np.array(p1, float)
    d = p1 - p0
    nrm = np.array([-d[1], d[0]])
    c = (p0 + p1) / 2 + nrm * bend
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * c + t ** 2 * p1


def draw_arrow(cv, p0, p1, color=None, progress=1.0, alpha=1.0, bend=0.25, thick=6):
    """곡선 화살표. progress 0→1 로 그려지며 진행."""
    color = color or ACCENT
    if progress <= 0.01:
        return
    pts = bezier(p0, p1, bend)
    k = max(3, int(len(pts) * clamp01(progress)))
    pts = pts[:k]
    tip = pts[-1]
    dirv = pts[-1] - pts[-3]
    dirv = dirv / (np.linalg.norm(dirv) + 1e-6)
    nv = np.array([-dirv[1], dirv[0]])
    hl = 26
    head = [tip + dirv * 4, tip - dirv * hl + nv * hl * 0.6, tip - dirv * hl * 0.7, tip - dirv * hl - nv * hl * 0.6]
    body = pts.copy()
    body[-1] = tip - dirv * hl * 0.7
    allp = np.vstack([pts, head])
    bb = (allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max())

    def fn(img, ox, oy):
        b = _p(body, ox, oy).astype(np.int32)
        h_ = _p(head, ox, oy).astype(np.int32)
        outline = [head[0] + dirv * 3, head[1] - nv * 3 - dirv * 2, head[2], head[3] + nv * 3 - dirv * 2]
        cv2.polylines(img, [b], False, (12, 14, 20, 200), thick + 6, cv2.LINE_AA, SH)
        cv2.fillPoly(img, [_p(outline, ox, oy).astype(np.int32)], (12, 14, 20, 200), cv2.LINE_AA, SH)
        cv2.polylines(img, [b], False, rgba(color), thick, cv2.LINE_AA, SH)
        cv2.fillPoly(img, [h_], rgba(color), cv2.LINE_AA, SH)

    cv.shape(bb, fn, alpha, glow=0)


def dim_outside(frame, rect, strength, feather=40, radius=24):
    """rect(화면 좌표) 바깥을 어둡게 — 스포트라이트."""
    if strength <= 0.003:
        return frame
    s = 4
    m = np.zeros((H // s, W // s), np.float32)
    x0, y0, x1, y1 = [v / s for v in rect]
    pts = np.array(rrect_pts(x0, y0, x1, y1, radius / s), np.float64) * SC
    cv2.fillPoly(m, [pts.astype(np.int32)], 1.0, cv2.LINE_AA, SH)
    m = cv2.GaussianBlur(m, (0, 0), feather / s)
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
    k = 1.0 - strength * (1.0 - m)
    return (frame.astype(np.float32) * k[..., None]).astype(np.uint8)
