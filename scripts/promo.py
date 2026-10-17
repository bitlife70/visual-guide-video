"""광고·홍보 영상 연출 (PROFILE='promo' 의 핵심 도구, 다른 프로필에서도 동작).

CLEANUP    원본에 박힌 글씨·도장·로고 지우기 (다른 언어판·재편집). 원본 시각·원본 좌표.
           (t0, t1, (x0, y0, x1, y1), dict(plate=(ta, tb), ref=t, ink="dark"|"light", seal=True, k=31, thr=26, grow=6,
                                          mask="text"|"box", live=False))
           - plate: 같은 장면에서 글씨가 없는 프레임의 원본 시각(1개 이상). 둘 이상이면 시간에 따라 섞어 배경 변화를 따라간다.
           - plate 가 없으면 cv2.inpaint 로 메운다 → 단색 띠·하늘처럼 단순한 배경에만 쓴다.
           - ref: 글씨가 또렷한 시각(마스크를 만든다, 기본 구간 가운데). live=True 면 매 프레임 마스크를 다시 만든다(움직이는 글씨).
TYPE       광고 타이포. 시각은 원본 시각(또는 (시각, 오프셋)), 좌표는 디자인 캔버스(기본 1920x1080, 세로 쇼츠 1080x1920).
           (t0, t1, "hero",    dict(text="KOREA", sub="...", kicker="...", pos=(960, 420), size=190))
           (t0, t1, "chapter", dict(kicker="SPRING", title="Sunrise over the East Sea", seal="春", pos=(1840, 170), align="right"))
           (t0, t1, "line",    dict(text="There is a land", pos=(960, 540), size=64, italic=True))
           (t0, t1, "slam",    dict(text="SPRING", pos=(540, 900), size=180, seal="春"))   — 쇼츠: 박자에 맞춰 쾅
           공통 옵션: color(RGB), halo=(RGB, 반경, 불투명도) 또는 None, sfx=[(이름, 오프셋초, gain)], chapter 는 pace(등장 속도)
           빨리감기 구간에서는 원본 초가 짧아지므로 (원본 시각, 출력 오프셋초) 로 '출력 기준' 시각을 쓰면 편하다.
GLOWS      빛 번짐 + 렌즈 플레어: (t0, t1, 대상, dict(radius=240, color=(255, 170, 90), strength=0.5, flare=True, pulse=0.08))
INK        먹물 번짐 전환: (t, dict(dur=1.4, at=(x, y) 원본 좌표 | "center", color=(16, 16, 20))) — t 에 화면이 가장 많이 덮인다.
LETTERBOX  시네마 레터박스: dict(ratio=2.39, range=(t0, t1))
"""
import math
import os
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import gfx
from gfx import Sprite, clamp01, ease_io, ease_out, window

W, H = gfx.W, gfx.H
TL = None


def _find(env, candidates, fallback):
    p = os.environ.get(env)
    if p and os.path.exists(p):
        return p
    for c in candidates:
        if os.path.exists(c):
            return c
    return fallback


# 광고 타이포 폰트 — 없으면 기본 폰트로 대체
FONT_SERIF = _find("VGUIDE_FONT_SERIF", [
    "C:/Windows/Fonts/SitkaVF.ttf", "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/cambria.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/opentype/noto/NotoSerif-Regular.ttf",
], gfx.FONT_R)
FONT_SERIF_I = _find("VGUIDE_FONT_SERIF_ITALIC", [
    "C:/Windows/Fonts/SitkaVF-Italic.ttf", "C:/Windows/Fonts/georgiai.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
], FONT_SERIF)
FONT_LIGHT = _find("VGUIDE_FONT_LIGHT", [
    "C:/Windows/Fonts/segoeuil.ttf", "C:/Windows/Fonts/segoeuisl.ttf", "/System/Library/Fonts/Avenir Next.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf",
], gfx.FONT_R)
FONT_CJK_SERIF = _find("VGUIDE_FONT_CJK_SERIF", [
    "C:/Windows/Fonts/HANBatangB.ttf", "C:/Windows/Fonts/batang.ttc", "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
], gfx.FONT_B)
FAMILY = {"serif": FONT_SERIF, "italic": FONT_SERIF_I, "light": FONT_LIGHT, "cjk": FONT_CJK_SERIF}

INK = (38, 32, 28)
PAPER = (246, 240, 226)
SEAL_RED = (178, 34, 30)


@lru_cache(None)
def _font(path, size, variation=None):
    f = ImageFont.truetype(path, size)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


def _f(family, size):
    path = FAMILY.get(family, family)
    var = None
    if "Sitka" in os.path.basename(path):
        var = "Banner" if size >= 70 else "Display" if size >= 40 else "Subheading"
    return _font(path, int(size), var)


# ================================================================ 텍스트 스프라이트
@lru_cache(4096)
def text_sprite(text, family="serif", size=60, color=INK, tracking=0.0, halo=(PAPER, 16, 0.55)):
    """자간(tracking, em 단위)을 줄 수 있는 한 줄 텍스트. halo = (색, 반경, 불투명도) — 그림 위 가독성."""
    f = _f(family, size)
    adv = [f.getlength(ch) for ch in text]
    tr = tracking * size
    width = int(sum(adv) + tr * max(0, len(text) - 1)) + 4
    asc, desc = f.getmetrics()
    h = asc + desc + 4
    pad = int(halo[1] * 2.2) + 4 if halo else 4
    img = Image.new("RGBA", (width + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for ch, a in zip(text, adv):
        d.text((x, pad), ch, font=f, fill=(*color, 255))
        x += a + tr
    if halo:
        hc, hr, ho = halo
        al = img.split()[3].filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(hr))
        al = al.point(lambda v: int(min(255, v * ho * 2.2)))
        base = Image.new("RGBA", img.size, (*hc, 0))
        base.putalpha(al)
        base.alpha_composite(img)
        img = base
    return Sprite(img, pad)


@lru_cache(64)
def seal_sprite(char, size=86, color=SEAL_RED, seed=3):
    """낙관(붉은 도장): 흰 글자를 판 사각 도장 + 인주 번짐 질감."""
    s = size * 3
    img = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(img)
    m = s * 0.06
    d.rounded_rectangle([m, m, s - m, s - m], s * 0.08, fill=255)
    f = _font(FONT_CJK_SERIF, int(s * (0.62 if len(char) == 1 else 0.36)))
    if len(char) == 1:
        bb = d.textbbox((0, 0), char, font=f)
        d.text(((s - bb[2] - bb[0]) / 2, (s - bb[3] - bb[1]) / 2), char, font=f, fill=0)
    else:  # 2x2 배치 (예: "錦繡江山" → 오른쪽 열부터 위→아래)
        for i, ch in enumerate(char[:4]):
            col, row = 1 - i // 2, i % 2
            bb = d.textbbox((0, 0), ch, font=f)
            cx, cy = s * (0.3 + 0.4 * col), s * (0.3 + 0.4 * row)
            d.text((cx - (bb[2] + bb[0]) / 2, cy - (bb[3] + bb[1]) / 2), ch, font=f, fill=0)
    a = np.asarray(img, np.float32) / 255
    r = np.random.default_rng(seed)
    grain = cv2.GaussianBlur(r.random((s, s)).astype(np.float32), (0, 0), 2.2)
    a = a * np.clip((grain - 0.28) * 4.5, 0, 1)  # 인주가 덜 묻은 자리
    a = cv2.resize(a, (size, size), interpolation=cv2.INTER_AREA)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = np.clip(a * 255 * 0.95, 0, 255).astype(np.uint8)
    return Sprite(Image.fromarray(rgba, "RGBA"), 0)


@lru_cache(32)
def veil_sprite(w, h, color=PAPER):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a = np.clip(1 - d, 0, 1) ** 0.8
    a = np.clip(a * 1.6, 0, 1)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = color
    rgba[..., 3] = (a * 255).astype(np.uint8)
    return Sprite(Image.fromarray(rgba, "RGBA"), 0)


def _halo(opt, default=(PAPER, 16, 0.55)):
    h = opt.get("halo", default)
    return tuple(h) if h else None


# ================================================================ TYPE 레이어
def _hero(cv, t, a0, a1, opt):
    w = window(t, a0, a1, 0.01, 0.7)
    if not w:
        return
    al_out = w[0]
    u = clamp01((t - a0) / 1.6)
    col = tuple(opt.get("color", INK))
    halo = _halo(opt, (PAPER, 22, 0.6))
    x, y = opt.get("pos", (W / 2, H / 2))
    size = opt.get("size", 190)
    tk0, tk1 = opt.get("tracking", (0.95, 0.32))
    tk = round(tk1 + (tk0 - tk1) * (1 - ease_out(u)) + 0.08 * (1 - al_out), 3)
    sp = text_sprite(opt["text"], opt.get("font", "light"), size, col, tk, halo)
    cv.sprite(sp, x, y, ease_out(u) * al_out)
    if opt.get("seal"):  # 제목 오른쪽에 낙관
        ssz = opt.get("seal_size", int(size * 0.5))
        k = clamp01((t - a0 - opt.get("seal_t", 1.1)) / 0.2)
        if k > 0:
            fin = text_sprite(opt["text"], opt.get("font", "light"), size, col, tk1, halo).body[0]
            sx = x + fin / 2 + ssz * 0.5 + opt.get("seal_gap", 24)
            cv.sprite(seal_sprite(opt["seal"], ssz), sx, y + opt.get("seal_dy", 0), min(1, k * 1.6) * al_out, 1 + 0.9 * (1 - k) ** 2)
    if opt.get("kicker"):
        k = clamp01((t - a0 - 0.35) / 0.8)
        ks = text_sprite(opt["kicker"], "light", opt.get("kicker_size", 30), col, 0.55, halo)
        cv.sprite(ks, x + opt.get("kicker_size", 30) * 0.275, y - size * 0.72 - 12 * (1 - ease_out(k)), ease_out(k) * al_out)
    for i, line in enumerate([opt["sub"]] if isinstance(opt.get("sub"), str) else opt.get("sub", [])):
        k = clamp01((t - a0 - 0.8 - 0.25 * i) / 0.8)
        fam, sz = ("italic", opt.get("sub_size", 44)) if i == 0 else ("light", opt.get("sub2_size", 26))
        ss = text_sprite(line, fam, sz, col, 0.02 if i == 0 else 0.4, halo)
        cv.sprite(ss, x, y + size * 0.72 + i * 64 + 16 * (1 - ease_out(k)), ease_out(k) * al_out)
    if opt.get("rule", True) and opt.get("sub"):
        k = ease_io(clamp01((t - a0 - 0.6) / 0.9))
        half = opt.get("rule_w", 260) * k
        yy = y + size * 0.5
        fx_line(cv, (x - half, yy), (x + half, yy), col, 2, 0.8 * al_out)


def fx_line(cv, p0, p1, color, thick, alpha):
    if p1[0] - p0[0] < 1:
        return
    def fn(img, ox, oy):
        a = (int((p0[0] - ox) * gfx.SC), int((p0[1] - oy) * gfx.SC))
        b = (int((p1[0] - ox) * gfx.SC), int((p1[1] - oy) * gfx.SC))
        cv2.line(img, a, b, gfx.rgba(color), thick, cv2.LINE_AA, gfx.SH)
    cv.shape((p0[0], p0[1] - 2, p1[0], p1[1] + 2), fn, alpha)


def _chapter(cv, t, a0, a1, opt):
    w = window(t, a0, a1, 0.01, 0.5)
    if not w:
        return
    al = w[0]
    p = opt.get("pace", 1.0)  # 등장 애니메이션 속도 배율 (쇼츠 0.5~0.6)
    lift = -14 * (1 - al)
    col = tuple(opt.get("color", INK))
    halo = _halo(opt)
    x, y = opt.get("pos", (W - 80, 160))
    right = opt.get("align", "right") == "right"
    ksz, tsz, ssz = opt.get("kicker_size", 28), opt.get("size", 58), opt.get("seal_size", 92)
    title = text_sprite(opt["title"], opt.get("font", "serif"), tsz, col, 0.0, halo)
    tw = title.body[0]
    kick = text_sprite(opt.get("kicker", ""), "light", ksz, col, 0.6, halo) if opt.get("kicker") else None
    gap = 30
    has_seal = bool(opt.get("seal"))
    block_w = tw + (ssz + gap if has_seal else 0)
    x0 = x - block_w if right else x  # 블록 왼쪽 끝
    tx = x0 + (ssz + gap if has_seal else 0)
    if opt.get("veil"):  # 글자 뒤 안개 같은 종이색 베일 (복잡한 배경·지운 자국 가리기)
        va, vp = opt["veil"] if isinstance(opt["veil"], (tuple, list)) else (opt["veil"], 120)
        bh = ksz + 22 + title.body[1]
        cv.sprite(veil_sprite(int(block_w + 2 * vp), int(bh + 2 * vp), tuple(opt.get("veil_color", PAPER))),
                  x0 + block_w / 2, y + bh / 2 + lift, va * al)
    # 낙관: 크게 떨어져 내려 '쾅' 찍힘
    if has_seal:
        u = clamp01((t - a0 - 0.1 * p) / (0.2 * p))
        if u > 0:
            sc = 1 + 0.9 * (1 - u) ** 2
            cv.sprite(seal_sprite(opt["seal"], ssz), x0 + ssz / 2, y + ssz / 2 + lift, min(1, u * 1.6) * al, sc)
    if kick:
        k = clamp01((t - a0 - 0.3 * p) / (0.7 * p))
        cv.sprite(kick, tx, y + 8 + lift, ease_out(k) * al, anchor=(0, 0))
        kw = kick.body[0]
        r = ease_io(clamp01((t - a0 - 0.45 * p) / (0.8 * p)))
        yy = y + 8 + ksz * 0.75
        fx_line(cv, (tx + kw + 18, yy + lift), (tx + kw + 18 + max(0, tw - kw - 18) * r, yy + lift), col, 2, 0.7 * al)
    k = clamp01((t - a0 - 0.55 * p) / (0.8 * p))
    cv.sprite(title, tx, y + ksz + 22 + 18 * (1 - ease_out(k)) + lift, ease_out(k) * al, anchor=(0, 0))


def _line(cv, t, a0, a1, opt):
    w = window(t, a0, a1, 0.01, 0.6)
    if not w:
        return
    al = w[0]
    col = tuple(opt.get("color", INK))
    halo = _halo(opt)
    size = opt.get("size", 60)
    fam = "italic" if opt.get("italic") else opt.get("font", "serif")
    words = opt["text"].split(" ")
    f = _f(fam, size)
    space = f.getlength(" ") + size * opt.get("tracking", 0.0)
    sps = [text_sprite(wd, fam, size, col, opt.get("tracking", 0.0), halo) for wd in words]
    total = sum(s.body[0] for s in sps) + space * (len(sps) - 1)
    x, y = opt.get("pos", (W / 2, H / 2))
    ax = {"center": 0.5, "left": 0.0, "right": 1.0}[opt.get("align", "center")]
    cx = x - total * ax
    stag = opt.get("stagger", 0.14)
    for i, s in enumerate(sps):
        k = clamp01((t - a0 - i * stag) / 0.7)
        cv.sprite(s, cx, y + 18 * (1 - ease_out(k)), ease_out(k) * al, anchor=(0, 0.5))
        cx += s.body[0] + space


def _slam(cv, t, a0, a1, opt):
    """쇼츠용: 큰 단어가 박자에 맞춰 '쾅' 커졌다 자리 잡고 천천히 밀려 들어간다."""
    w = window(t, a0, a1, 0.01, opt.get("fade", 0.3))
    if not w:
        return
    u = clamp01((t - a0) / opt.get("in", 0.16))
    push = 0.05 * clamp01((t - a0) / max(0.01, a1 - a0))
    sc = 1 + opt.get("punch", 0.4) * (1 - ease_out(u)) + push
    sp = text_sprite(opt["text"], opt.get("font", "light"), opt.get("size", 180), tuple(opt.get("color", INK)),
                     opt.get("tracking", 0.18), _halo(opt, (PAPER, 22, 0.6)))
    x, y = opt.get("pos", (W / 2, H / 2))
    cv.sprite(sp, x, y, ease_out(u) * w[0], sc)
    if opt.get("seal"):
        ssz = opt.get("seal_size", 96)
        k = clamp01((t - a0 - opt.get("seal_t", 0.22)) / 0.16)
        if k > 0:
            cv.sprite(seal_sprite(opt["seal"], ssz), x, y + sp.body[1] * 0.5 * sc + ssz * 0.75, min(1, k * 1.6) * w[0],
                      1 + 0.9 * (1 - k) ** 2)


TYPE_FN = {"hero": _hero, "chapter": _chapter, "line": _line, "slam": _slam}


def _on_top(style, opt):
    return opt.get("over_ink", style == "slam")


def layer_type(cv, t, top=False):
    """top=False: 일반 타이포 (먹물·레터박스 아래). top=True: 먹물 위에 그릴 항목 (slam 기본)."""
    for a0, a1, style, opt in TL.type_items:
        if _on_top(style, opt) == top:
            TYPE_FN[style](cv, t, a0, a1, opt)


_TOP = None


def overlay_top(out, t):
    """먹물 전환 위에 그리는 타이포(slam 등)를 따로 합성."""
    global _TOP
    if not any(_on_top(s, o) and a0 - 0.05 <= t <= a1 + 0.5 for a0, a1, s, o in TL.type_items):
        return out
    if _TOP is None:
        _TOP = gfx.Canvas()
    _TOP.clear()
    layer_type(_TOP, t, top=True)
    return _TOP.composite(out)


# ================================================================ CLEANUP (원본 프레임 단계)
def _read(src, ts):
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(ts * cap.get(cv2.CAP_PROP_FPS))))
    ok, f = cap.read()
    cap.release()
    return f if ok else None


def _text_mask(crop, opt):
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    k = int(opt.get("k", 31)) | 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    op = cv2.MORPH_TOPHAT if opt.get("ink", "dark") == "light" else cv2.MORPH_BLACKHAT
    m = (cv2.morphologyEx(g, op, ker) > opt.get("thr", 26)).astype(np.uint8)
    if opt.get("seal", True):  # 붉은 도장 (주홍빛 하늘·노을은 제외: 초록·파랑이 낮은 진한 빨강만)
        c = crop.astype(np.int16)
        m |= ((c[..., 2] > 120) & (c[..., 1] < 105) & (c[..., 0] < 105) & (c[..., 2] - c[..., 1] > 70)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros(n, np.uint8)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= opt.get("min_area", 8)
    m = keep[lab]
    gr = int(opt.get("grow", 6))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gr + 1, 2 * gr + 1)))
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, gr / 2))
    return np.clip(a * 1.6, 0, 1)


def _box_mask(h, w, feather=10):
    a = np.zeros((h, w), np.float32)
    a[feather:h - feather, feather:w - feather] = 1
    return cv2.GaussianBlur(a, (0, 0), feather / 2)


def _prep(gray_big, hole):
    g = gray_big.astype(np.float32).copy()
    g[hole] = g[~hole].mean() if (~hole).any() else 0
    g = g - cv2.GaussianBlur(g, (0, 0), 25)  # 큰 밝기 변화(노을·조명) 제거 → 무늬로만 맞춘다
    return g * cv2.createHanningWindow((g.shape[1], g.shape[0]), cv2.CV_32F)


class _Clean:
    """plate 를 쓰는 경우 장면이 천천히 움직이면(패닝·줌) plate 를 위상 상관으로 따라 움직여 맞춘다(align=True)."""

    def __init__(self, item, src, cache_dir):
        self.t0, self.t1, box, self.opt = item
        self.box = [int(v) for v in box]
        x0, y0, x1, y1 = self.box
        info_w, info_h = TL.info["w"], TL.info["h"]
        M = int(self.opt.get("margin", 90))
        self.big = (max(0, x0 - M), max(0, y0 - M), min(info_w, x1 + M), min(info_h, y1 + M))
        bx0, by0, bx1, by1 = self.big
        self.inner = (x0 - bx0, y0 - by0, x1 - bx0, y1 - by0)
        plates = self.opt.get("plate")
        plates = [plates] if isinstance(plates, (int, float)) else list(plates or [])
        self.plates = []
        for tp in plates:
            f = _read(src, tp)
            if f is not None:
                self.plates.append((tp, f[by0:by1, bx0:bx1].copy()))
        self.live = self.opt.get("live", False)
        self.mask = None
        if self.opt.get("mask") == "box":
            self.mask = _box_mask(y1 - y0, x1 - x0, self.opt.get("feather", 10))
        elif not self.live:
            ref = _read(src, self.opt.get("ref", (self.t0 + self.t1) / 2))
            self.mask = _text_mask(ref[y0:y1, x0:x1], self.opt) * _box_mask(y1 - y0, x1 - x0, 6)  # 상자 경계 이음새 방지
        self.fits = None
        if self.plates and self.mask is not None and self.opt.get("align", True):
            self.fits = self._align(src, cache_dir)

    def _hole(self):
        hole = np.zeros((self.big[3] - self.big[1], self.big[2] - self.big[0]), bool)
        ix0, iy0, ix1, iy1 = self.inner
        hole[iy0:iy1, ix0:ix1] = cv2.dilate((self.mask > 0.05).astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
        return hole

    def _align(self, src, cache_dir):
        """plate → 현재 프레임 이동량을 0.25초 간격으로 재고 시간에 대한 2차식으로 매끈하게 맞춘다 (캐시)."""
        import hashlib
        key = hashlib.md5(repr((os.path.abspath(src), self.t0, self.t1, self.box, sorted(
            (k, v) for k, v in self.opt.items() if k != "sfx"))).encode()).hexdigest()[:16]
        path = os.path.join(cache_dir, f"clean_{key}.npy")
        if os.path.exists(path):
            return np.load(path)
        hole = self._hole()
        bx0, by0, bx1, by1 = self.big
        P = [_prep(cv2.cvtColor(p, cv2.COLOR_BGR2GRAY), hole) for _, p in self.plates]
        cap = cv2.VideoCapture(src)
        fps = cap.get(cv2.CAP_PROP_FPS)
        i0, i1 = int(self.t0 * fps), int(self.t1 * fps)
        step = max(1, int(round(fps * 0.25)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, i0)
        samples = [[] for _ in P]
        for i in range(i0, i1 + 1):
            ok, f = cap.read()
            if not ok:
                break
            if (i - i0) % step:
                continue
            C = _prep(cv2.cvtColor(f[by0:by1, bx0:bx1], cv2.COLOR_BGR2GRAY), hole)
            for k, pk in enumerate(P):
                (dx, dy), r = cv2.phaseCorrelate(pk, C)
                samples[k].append((i / fps, dx, dy, r))
        cap.release()
        fits = []
        for k, (tp, _) in enumerate(self.plates):
            s = np.array(samples[k] + [(tp, 0.0, 0.0, 1.0)] * 3)  # plate 시각에서는 이동 0
            good = (s[:, 3] > 0.08) & (np.abs(s[:, 1]) < 150) & (np.abs(s[:, 2]) < 150)
            s = s[good]
            deg = 2 if len(s) >= 6 else 0
            w = np.clip(s[:, 3], 0.05, 1)
            fits.append([np.polyfit(s[:, 0], s[:, 1], deg, w=w), np.polyfit(s[:, 0], s[:, 2], deg, w=w)])
        fits = np.array([[np.pad(c, (3 - len(c), 0)) for c in f] for f in fits])
        os.makedirs(cache_dir, exist_ok=True)
        np.save(path, fits)
        return fits

    def _plate_at(self, k, ts):
        tp, p = self.plates[k]
        ix0, iy0, ix1, iy1 = self.inner
        if self.fits is None:
            return p[iy0:iy1, ix0:ix1].astype(np.float32)
        dx, dy = np.polyval(self.fits[k][0], ts), np.polyval(self.fits[k][1], ts)
        Mx = np.float32([[1, 0, dx], [0, 1, dy]])
        q = cv2.warpAffine(p, Mx, (p.shape[1], p.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return q[iy0:iy1, ix0:ix1].astype(np.float32)

    def plate(self, ts):
        ps = self.plates
        if len(ps) == 1 or ts <= ps[0][0]:
            return self._plate_at(0, ts)
        for k in range(len(ps) - 1):
            ta, tb = ps[k][0], ps[k + 1][0]
            if ts <= tb:
                u = (ts - ta) / max(1e-6, tb - ta)
                return self._plate_at(k, ts) * (1 - u) + self._plate_at(k + 1, ts) * u
        return self._plate_at(len(ps) - 1, ts)

    def apply(self, frame, ts):
        if not (self.t0 <= ts <= self.t1):
            return frame
        x0, y0, x1, y1 = self.box
        crop = frame[y0:y1, x0:x1]
        m = _text_mask(crop, self.opt) if self.live else self.mask
        if self.plates:
            fill = self.plate(ts)
        else:  # NS 인페인트는 주변 선의 방향을 이어 준다 + 종이 질감(고정 무늬)을 얹어 매끈한 얼룩을 숨긴다
            hole = (m > 0.25).astype(np.uint8)
            method = cv2.INPAINT_NS if self.opt.get("method", "ns") == "ns" else cv2.INPAINT_TELEA
            fill = cv2.inpaint(crop, hole, self.opt.get("radius", 7), method).astype(np.float32)
            if self.opt.get("grain", True) and (hole == 0).any():
                g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
                sd = float((g - cv2.GaussianBlur(g, (0, 0), 2))[hole == 0].std())
                if not hasattr(self, "_grain"):
                    r = np.random.default_rng(5)
                    self._grain = cv2.GaussianBlur(r.standard_normal(g.shape).astype(np.float32), (0, 0), 0.8)
                    self._grain /= self._grain.std() + 1e-6
                fill += (self._grain * sd)[..., None]
        frame = frame.copy()
        a = m[..., None]
        frame[y0:y1, x0:x1] = np.clip(crop * (1 - a) + fill * a + 0.5, 0, 255).astype(np.uint8)
        return frame


def cleanup(frame, ts):
    for c in TL._cleans:
        frame = c.apply(frame, ts)
    return frame


# ================================================================ GLOWS
def _screen_blend(img, x0, y0, glow_rgb):
    """img(BGR uint8)의 (x0, y0) 영역에 glow_rgb(h, w, 3 float 0..1, RGB)를 스크린 블렌드."""
    h, w = glow_rgb.shape[:2]
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if X1 <= X0 or Y1 <= Y0:
        return
    g = glow_rgb[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0, ::-1]
    d = img[Y0:Y1, X0:X1].astype(np.float32) / 255
    img[Y0:Y1, X0:X1] = np.clip((1 - (1 - d) * (1 - g)) * 255 + 0.5, 0, 255).astype(np.uint8)


def glows(img, view, t, ts):
    act = [(g, w) for g in TL.glows for w in [window(t, g[0], g[1], 0.8, 0.8)] if w]
    if not act:
        return img
    img = img.copy()
    for (a0, a1, tgt, opt), w in act:
        al = w[0]
        cx, cy = view.s(tgt.pt(ts))
        z = getattr(view, "z", 1.0)
        r = opt.get("radius", 240) * TL.scale * z  # 반경은 원본 픽셀 기준
        col = np.array(opt.get("color", (255, 170, 90)), np.float32) / 255
        s = opt.get("strength", 0.5) * al * (1 + opt.get("pulse", 0.08) * math.sin(t * 2.1))
        R = int(r * 2.6)
        yy, xx = np.mgrid[-R:R, -R:R].astype(np.float32)
        d2 = (xx ** 2 + yy ** 2) / (r * r)
        g = np.exp(-d2 * 0.9) * 0.55 + np.exp(-d2 * 6) * 0.45
        _screen_blend(img, int(cx) - R, int(cy) - R, (g * s)[..., None] * col)
        if opt.get("flare", True):
            sy = max(2.0, r * 0.035)
            hh = int(sy * 4)
            ys = np.arange(-hh, hh, dtype=np.float32)[:, None]
            xs = np.arange(W, dtype=np.float32)[None, :] - cx
            streak = np.exp(-(ys / sy) ** 2) * np.exp(-np.abs(xs) / (r * 4.5))
            fc = np.array(opt.get("flare_color", (255, 214, 170)), np.float32) / 255
            _screen_blend(img, 0, int(cy) - hh, (streak * s * 0.7)[..., None] * fc)
            vx, vy = W / 2 - cx, H / 2 - cy
            for k, rr, aa, c in ((0.55, 0.16, 0.10, (255, 200, 140)), (1.15, 0.32, 0.06, (150, 200, 255)),
                                 (1.6, 0.1, 0.09, (255, 160, 200)), (1.95, 0.45, 0.04, (180, 255, 210))):
                gx, gy, gr = cx + vx * k, cy + vy * k, r * rr
                Rg = int(gr * 1.3) + 2
                y2, x2 = np.mgrid[-Rg:Rg, -Rg:Rg].astype(np.float32)
                dd = np.sqrt(x2 ** 2 + y2 ** 2) / gr
                disk = np.clip((1 - dd) / 0.15, 0, 1) * (0.6 + 0.4 * dd)
                _screen_blend(img, int(gx) - Rg, int(gy) - Rg, (disk * aa * s * 2)[..., None] * (np.array(c) / 255))
    return img


# ================================================================ INK 먹물 전환
@lru_cache(None)
def _noise(seed):
    r = np.random.default_rng(seed)
    acc = np.zeros((H, W), np.float32)
    for scale, amp in ((64, 0.55), (24, 0.3), (8, 0.15)):
        n = r.random((H // scale + 2, W // scale + 2)).astype(np.float32)
        acc += cv2.resize(n, (W, H), interpolation=cv2.INTER_CUBIC)[:H, :W] * amp
    return (acc - acc.min()) / (acc.max() - acc.min())


@lru_cache(None)
def _dist(cx, cy):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    return d / d.max()


def ink(out, t):
    for i, (tm, opt) in enumerate(TL.inks):
        dur = opt.get("dur", 1.4)
        p = (t - (tm - dur / 2)) / dur
        if not (0 <= p <= 1):
            continue
        at = opt.get("at", "center")
        cx, cy = (W / 2, H / 2) if at == "center" else TL.P(at)
        nz = _noise(17 + i)
        de = _dist(int(cx), int(cy)) * 0.85 + (nz - 0.5) * 0.42 + 0.12
        fe = 0.07
        if p < 0.5:
            q = ease_io(p / 0.5) * 1.25
            a = np.clip((q - de) / fe, 0, 1)
        else:
            q = ease_io((p - 0.5) / 0.5) * 1.25
            a = np.clip((de - q) / fe, 0, 1)
        a *= opt.get("opacity", 0.97)
        col = np.array(opt.get("color", (16, 16, 20))[::-1], np.float32)
        tone = col[None, None, :] + (nz[..., None] - 0.5) * 36  # 먹의 농담
        f = out.astype(np.float32)
        out = np.clip(f + (tone - f) * a[..., None], 0, 255).astype(np.uint8)
    return out


# ================================================================ LETTERBOX
def bars(img, t):
    lb = TL.letterbox
    if not lb:
        return img
    w = window(t, *lb["range"], lb.get("fade", 0.9), lb.get("fade", 0.9))
    if not w:
        return img
    hb = int(round((H - W / lb.get("ratio", 2.39)) / 2 * ease_io(w[0])))
    if hb <= 0:
        return img
    img = img.copy()
    img[:hb] = 0
    img[H - hb:] = 0
    return img


# ================================================================ 로딩 / 효과음
def load(t, g, T, span, O):
    t.cleanups = [(c[0], c[1], c[2], c[3] if len(c) > 3 else {}) for c in g("CLEANUP", []) or []]
    t.type_items = [(*span(x[0], x[1]), x[2], x[3]) for x in g("TYPE", []) or []]
    t.glows = [(*span(x[0], x[1]), T(x[2]), x[3] if len(x) > 3 else {}) for x in g("GLOWS", []) or []]
    t.inks = [(O(x[0]), x[1] if len(x) > 1 else {}) for x in g("INK", []) or []]
    lb = g("LETTERBOX")
    if lb:
        lb = dict(lb)
        lb["range"] = span(*lb["range"]) if lb.get("range") else (0.0, t.duration)
    t.letterbox = lb


def setup(tl):
    global TL
    TL = tl
    tl._cleans = [_Clean(c, tl.src, os.path.join(tl.build_dir, "cleanup_cache")) for c in tl.cleanups]


DEFAULT_SFX = {"chapter": [("stamp", 0.28, 0.8)], "hero": [], "line": [], "slam": [("stamp", 0.02, 0.7)]}


def add_sfx(tl, buf, add, make):
    """make(name) → 효과음 배열 (music.make_sfx, 'waves:6' 처럼 길이 인자 지원)."""
    for a0, a1, style, opt in tl.type_items:
        default = DEFAULT_SFX[style] + ([("stamp", opt.get("seal_t", 1.1) + 0.18, 0.8)] if style == "hero" and opt.get("seal") else [])
        pace = opt.get("pace", 1.0) if style == "chapter" else 1.0
        for name, off, gain in opt.get("sfx", default):
            add(buf, make(name), a0 + off * pace, 0.6 * gain)
    for tm, opt in tl.inks:
        if opt.get("sfx", True):
            add(buf, make("ink"), tm - opt.get("dur", 1.4) / 2, 0.5)
