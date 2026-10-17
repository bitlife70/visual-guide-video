"""범용 연출 효과 (게임·브이로그·애니메이션·화면녹화 공통).

프레임 효과   GRADE/GRADES 색보정, FREEZE 정지 화면 룩, IMPACTS 타격감(흔들림·플래시·방사 블러·색수차), FLASH, SHAKE
오버레이     MAGNIFY 돋보기, CALLOUTS 대상 추적 말풍선, POPS 팝업 텍스트, STICKERS 이모지 스티커, 속도 배지
"""
import math
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw

import gfx
from gfx import (Sprite, clamp01, draw_dot, draw_ring, ease_back, ease_io, ease_out, emoji_img, font, parse_rich,
                 pill_sprite, window, with_shadow)

W, H = gfx.W, gfx.H
TL = None


# ================================================================ 색보정
def _curve(x, contrast=0.0, lift=0.0, gain=1.0, gamma=1.0):
    y = np.clip(x * gain + lift, 0, 1) ** gamma
    if contrast:
        s = y * y * (3 - 2 * y)
        y = y + (s - y) * contrast * 2
    return np.clip(y, 0, 1)


def _split_tone(x, shadow, highlight):
    """shadow/highlight = (b, g, r) 가산치 (0..1)."""
    w_sh = (1 - x) ** 2
    w_hi = x ** 2
    return [np.clip(x + w_sh * shadow[c] + w_hi * highlight[c], 0, 1) for c in range(3)]


PRESETS = {
    # contrast, lift, gain(b,g,r), split tone(shadow bgr, highlight bgr), sat, vignette, bloom
    "cinematic": dict(contrast=0.14, gain=(1.0, 1.0, 1.02), tone=((0.05, 0.025, -0.02), (-0.05, 0.0, 0.05)), sat=1.1,
                      vig=0.32, bloom=0.10),
    "warm": dict(contrast=0.08, gain=(0.93, 1.0, 1.06), tone=((0, 0, 0.02), (-0.03, 0.01, 0.04)), sat=1.12, vig=0.2),
    "cool": dict(contrast=0.08, gain=(1.07, 1.01, 0.94), sat=0.95, vig=0.2),
    "vivid": dict(contrast=0.12, sat=1.35, vig=0.12),
    "mono": dict(contrast=0.2, sat=0.0, vig=0.35),
    "sepia": dict(contrast=0.1, sat=0.0, gain=(0.78, 0.93, 1.05), vig=0.35),
    "danger": dict(contrast=0.12, gain=(0.82, 0.86, 1.12), sat=0.75, vig=0.6),
    "dream": dict(contrast=-0.05, lift=0.05, sat=0.9, vig=0.1, bloom=0.4),
    "night": dict(contrast=0.1, gain=(1.08, 0.92, 0.82), gamma=1.15, sat=0.65, vig=0.4),
}


@lru_cache(None)
def _lut(name):
    p = PRESETS[name]
    x = np.arange(256) / 255.0
    base = _curve(x, p.get("contrast", 0), p.get("lift", 0), 1.0, p.get("gamma", 1.0))
    gain = p.get("gain", (1, 1, 1))
    chans = [np.clip(base * gain[c], 0, 1) for c in range(3)]
    if "tone" in p:
        sh, hi = p["tone"]
        toned = _split_tone(base, sh, hi)
        chans = [np.clip(chans[c] + (toned[c] - base), 0, 1) for c in range(3)]
    lut = np.stack(chans, axis=-1)  # (256, 3) BGR
    return (lut * 255 + 0.5).astype(np.uint8).reshape(256, 1, 3)


@lru_cache(None)
def _vignette(power=2.2):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    return np.clip(d, 0, 1) ** power


def _bloom(img, amount):
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = cv2.subtract(small, np.full_like(small, 150))
    hi = cv2.GaussianBlur(hi, (0, 0), 9)
    up = cv2.resize(hi, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.addWeighted(img, 1.0, up, amount * 2.2, 0)


def grade(img, name, amount=1.0):
    if not name or amount <= 0.01:
        return img
    p = PRESETS[name]
    out = cv2.LUT(img, _lut(name))
    sat = p.get("sat", 1.0)
    if abs(sat - 1) > 1e-3:
        gray = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        out = cv2.addWeighted(out, sat, gray, 1 - sat, 0)
    if p.get("bloom"):
        out = _bloom(out, p["bloom"])
    if p.get("vig"):
        k = 1.0 - p["vig"] * _vignette()
        out = (out.astype(np.float32) * k[..., None]).astype(np.uint8)
    if amount < 0.99:
        out = cv2.addWeighted(img, 1 - amount, out, amount, 0)
    return out


# ================================================================ 타격감
IMPACT = {
    #        shake  flash color         flash  radial chroma red-vignette  zoom punch
    "hit": dict(shake=10, color=(255, 255, 255), flash=0.30, radial=0.0, chroma=4, red=0.0, punch=0.015),
    "heavy": dict(shake=22, color=(255, 240, 220), flash=0.45, radial=0.05, chroma=8, red=0.0, punch=0.04),
    "crit": dict(shake=30, color=(255, 70, 50), flash=0.55, radial=0.07, chroma=10, red=0.75, punch=0.05),
    "damage": dict(shake=14, color=(255, 40, 30), flash=0.25, radial=0.0, chroma=6, red=0.6, punch=0.02),
    "block": dict(shake=8, color=(190, 225, 255), flash=0.45, radial=0.0, chroma=3, red=0.0, punch=0.01),
    "parry": dict(shake=12, color=(255, 230, 140), flash=0.6, radial=0.04, chroma=5, red=0.0, punch=0.03),
}
SHAKE_DUR = 0.45


def _shake_wave(u, seed):
    r = np.random.default_rng(seed)
    ph = r.random(4) * 6.28
    f = 17 + r.random(2) * 8
    dx = math.sin(2 * math.pi * f[0] * u + ph[0]) + 0.5 * math.sin(2 * math.pi * f[1] * 1.7 * u + ph[1])
    dy = math.sin(2 * math.pi * f[1] * u + ph[2]) + 0.5 * math.sin(2 * math.pi * f[0] * 1.3 * u + ph[3])
    return dx / 1.5, dy / 1.5


def camera_offset(t):
    """(dx, dy, zoom 배율) — SHAKE + IMPACTS. render.View 가 적용."""
    dx = dy = 0.0
    zm = 1.0
    evs = [(ts, s, d) for ts, s, d in TL.shakes] + [(ti, IMPACT[k]["shake"], SHAKE_DUR) for ti, k in TL.impacts]
    for i, (ts, s, d) in enumerate(evs):
        u = t - ts
        if 0 <= u < d:
            env = math.exp(-u / d * 4.0) * (1 - u / d)
            wx, wy = _shake_wave(u, i * 7 + 3)
            dx += s * env * wx
            dy += s * env * wy
    for ti, k in TL.impacts:
        u = t - ti
        if 0 <= u < 0.35:
            zm *= 1 + IMPACT[k]["punch"] * math.exp(-u * 12) * min(1, u / 0.03 + 0.3)
    return dx, dy, zm


def _radial_blur(img, amount, center=(W / 2, H / 2)):
    acc = img.astype(np.float32) * 0.4
    for k, wgt in ((1, 0.25), (2, 0.2), (3, 0.15)):
        s = 1 + amount * k / 3
        M = np.float32([[s, 0, center[0] * (1 - s)], [0, s, center[1] * (1 - s)]])
        acc += cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE) * wgt
    return np.clip(acc, 0, 255).astype(np.uint8)


def _chroma(img, d):
    d = int(round(d))
    if d < 1:
        return img
    out = img.copy()
    out[:, d:, 2] = img[:, :-d, 2]
    out[:, :-d, 0] = img[:, d:, 0]
    return out


def _tint(img, color_rgb, a, mask=None):
    if a <= 0.004:
        return img
    c = np.array(color_rgb[::-1], np.float32)
    f = img.astype(np.float32)
    if mask is None:
        out = f + (c - f) * a
    else:
        m = (mask * a)[..., None]
        out = f + (c - f) * m
    return np.clip(out, 0, 255).astype(np.uint8)


def frame_fx(img, t):
    """카메라 적용 후 프레임에 색보정·정지 룩·타격감·플래시."""
    # 색보정: 구간 GRADES 가 있으면 그 구간에선 전역 GRADE 대신 사용
    name, amt = TL.grade, 1.0
    for a, b, p in TL.grades:
        w = window(t, a, b, 0.35, 0.35)
        if w:
            if w[0] >= 0.99 or not TL.grade:
                name, amt = p, w[0]
            else:
                img = grade(img, TL.grade, 1 - w[0])
                name, amt = p, w[0]
            break
    img = grade(img, name, amt)
    # 정지 화면: 채도 낮추고 흰 테두리
    for a, b, label, opt in TL.freezes:
        w = window(t, a, b, 0.12, 0.15)
        if w:
            look = opt.get("look", "desat")  # desat: 채도↓(분석·해설), photo: 셔터 플래시만(추억·사진), none
            if look == "desat":
                gray = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                img = cv2.addWeighted(img, 1 - 0.45 * w[0], gray, 0.45 * w[0], 0)
            u = t - a
            if look != "none" and u < 0.25:
                img = _tint(img, (255, 255, 255), (0.85 if look == "photo" else 0.7) * (1 - u / 0.25))
    # 타격감
    for ti, k in TL.impacts:
        u = t - ti
        if not (0 <= u < 0.6):
            continue
        p = IMPACT[k]
        if p["radial"] and u < 0.22:
            img = _radial_blur(img, p["radial"] * (1 - u / 0.22))
        if p["chroma"] and u < 0.3:
            img = _chroma(img, p["chroma"] * (1 - u / 0.3))
        if p["red"]:
            img = _tint(img, (200, 0, 0), p["red"] * 0.55 * math.exp(-u * 4), _vignette(1.6))
        if u < 0.25:
            img = _tint(img, p["color"], p["flash"] * (1 - u / 0.25) ** 2)
    for tf, color, strength, dur in TL.flashes:
        u = t - tf
        if 0 <= u < dur:
            img = _tint(img, color, strength * (1 - u / dur) ** 2)
    return img


# ================================================================ 오버레이 도구
def draw_line(cv, p0, p1, color, thick=3, alpha=1.0, glow=0):
    def fn(img, ox, oy):
        a = (int((p0[0] - ox) * gfx.SC), int((p0[1] - oy) * gfx.SC))
        b = (int((p1[0] - ox) * gfx.SC), int((p1[1] - oy) * gfx.SC))
        cv2.line(img, a, b, gfx.rgba(color), thick, cv2.LINE_AA, gfx.SH)

    cv.shape((min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1])), fn, alpha, glow)


COLOR_STYLES = {  # 말풍선 (글자색, 배경색)
    "white": (gfx.INK, gfx.WHITE), "dark": (gfx.WHITE, (16, 18, 27, 235)), "accent": (gfx.INK, None),
    "cyan": (gfx.INK, None), "green": (gfx.INK, None), "red": (gfx.WHITE, (232, 58, 58)), "yellow": (gfx.INK, (255, 214, 64)),
}


def _bubble_colors(name):
    fg, bg = COLOR_STYLES.get(name, COLOR_STYLES["white"])
    if bg is None:
        bg = gfx.COLORS[name]
    return fg, bg


def _line_color(name):
    return {"white": gfx.WHITE, "dark": gfx.WHITE, "red": (232, 58, 58), "yellow": (255, 214, 64)}.get(name) or gfx.COLORS.get(name, gfx.ACCENT)


def _clamp(x, y, bw, bh, m=24):
    return min(max(x, m), W - m - bw), min(max(y, m + 10), H - 120 - bh)


# ================================================================ 돋보기
@lru_cache(None)
def _disc(r, feather=1.5):
    y, x = np.mgrid[0:2 * r, 0:2 * r].astype(np.float32)
    d = np.sqrt((x - r + 0.5) ** 2 + (y - r + 0.5) ** 2)
    return np.clip((r - d) / feather, 0, 1)


def _lens(raw, src_c, r, k_src, sharpen=0.5):
    """원본 프레임 raw 에서 src_c 중심 반경 r/k_src 원본 px 영역을 지름 2r 로 확대한 premul RGBA."""
    rs = r / k_src
    M = np.float32([[k_src, 0, -k_src * (src_c[0] - rs)], [0, k_src, -k_src * (src_c[1] - rs)]])
    crop = cv2.warpAffine(raw, M, (2 * r, 2 * r), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if sharpen:
        blur = cv2.GaussianBlur(crop, (0, 0), 1.4)
        crop = cv2.addWeighted(crop, 1 + sharpen, blur, -sharpen, 0)
    m = _disc(r)
    rgb = crop[..., ::-1].astype(np.float32) / 255.0
    # 유리 하이라이트
    y = np.linspace(-1, 1, 2 * r, dtype=np.float32)[:, None]
    rgb = rgb + np.clip(-y - 0.35, 0, 1)[..., None] * 0.18
    out = np.empty((2 * r, 2 * r, 4), np.float32)
    out[..., :3] = np.clip(rgb, 0, 1) * m[..., None]
    out[..., 3] = m
    return out


def layer_magnify(cv, view, t, ts, raw):
    for a, b, tgt, zoom, label, opt in TL.magnify:
        w = window(t, a, b, 0.45, 0.3)
        if not w:
            continue
        al, u = w
        sx, sy = view.s(tgt.pt(ts))
        r = int(opt.get("r", 190))
        col = gfx.COLORS.get(opt.get("color", "accent"), gfx.ACCENT)
        # 확대 영역 표시 (대상 주변 원)
        tr = max(18, r / zoom)
        k_in = ease_out(clamp01((t - a) / 0.3))
        draw_ring(cv, (sx, sy), tr * (1.6 - 0.6 * k_in), gfx.WHITE, 3, al * 0.95)
        draw_ring(cv, (sx, sy), tr * (1.6 - 0.6 * k_in) + 4, col, 2, al * 0.8)
        # 렌즈 위치
        pos = opt.get("pos", "auto")
        if pos == "auto":
            lx = sx + (r + 230) * (1 if sx < W * 0.55 else -1)
            ly = sy - 40
        else:
            lx, ly = pos
        lx = min(max(lx, r + 30), W - r - 30)
        ly = min(max(ly, r + 40), H - r - 150)
        u2 = clamp01((t - a - 0.12) / 0.45)
        if u2 <= 0:
            continue
        rr = max(8, int(r * (0.25 + 0.75 * ease_back(u2))))
        z_now = 1 + (zoom - 1) * ease_io(clamp01((t - a - 0.2) / 0.6))
        k_src = (rr / r) * z_now * TL.scale * view.z
        # 연결선 → 그림자 → 렌즈 → 테두리
        d = np.array([lx - sx, ly - sy])
        n = d / (np.linalg.norm(d) + 1e-6)
        draw_line(cv, (sx + n[0] * tr, sy + n[1] * tr), (lx - n[0] * rr, ly - n[1] * rr), gfx.WHITE, 3, al * 0.9, glow=3)
        draw_dot(cv, (lx, ly + 10), rr + 4, (0, 0, 0), al * 0.45, glow=16)
        src_c = tgt.src_pt(ts)
        cv._over(_lens(raw, src_c, rr, k_src), int(lx - rr), int(ly - rr), al)
        draw_ring(cv, (lx, ly), rr, gfx.WHITE, 7, al)
        draw_ring(cv, (lx, ly), rr + 6, col, 3, al, )
        if label:
            sp = pill_sprite(label, size=30, fg=gfx.WHITE, bg=(16, 18, 27, 235), accent=col, padx=20, pady=9,
                             border=(*col, 255))
            bw, bh = sp.body
            cy = ly + rr + 22 + bh / 2
            if cy + bh / 2 > H - 120:
                cy = ly - rr - 22 - bh / 2
            cv.sprite(sp, lx, cy, al * clamp01((t - a - 0.35) / 0.25), 0.85 + 0.15 * ease_back(clamp01((t - a - 0.35) / 0.3)))
        z_badge = pill_sprite(f"🔍 x{zoom:g}", size=22, fg=gfx.WHITE, bg=(16, 18, 27, 225), padx=12, pady=5)
        cv.sprite(z_badge, lx + rr * 0.72, ly - rr * 0.78, al * clamp01((t - a - 0.4) / 0.25))


# ================================================================ 말풍선 (대상 추적)
def layer_callouts(cv, view, t, ts):
    for a, b, tgt, text, opt in TL.callouts:
        w = window(t, a, b, 0.28, 0.25)
        if not w:
            continue
        al, u = w
        sx, sy = view.s(tgt.pt(ts))
        style = opt.get("color", "white")
        fg, bg = _bubble_colors(style)
        sp = pill_sprite(text, size=opt.get("size", 32), fg=fg, bg=bg, padx=24, pady=12)
        bw, bh = sp.body
        side = opt.get("side", "auto")
        dist = opt.get("dist", 150)
        if side == "auto":
            side = "right" if sx < W * 0.5 else "left"
        if side == "right":
            bx, by = sx + dist, sy - dist * 0.7 - bh
        elif side == "left":
            bx, by = sx - dist - bw, sy - dist * 0.7 - bh
        elif side == "up":
            bx, by = sx - bw / 2, sy - dist - bh
        else:  # down
            bx, by = sx - bw / 2, sy + dist
        bx, by = _clamp(bx, by, bw, bh)
        sc = 0.6 + 0.4 * ease_back(u)
        cv.sprite(sp, bx + bw / 2, by + bh / 2, al, sc)
        # 꼬리 화살표: 말풍선 가장자리 → 대상
        p0 = (min(max(sx, bx + 20), bx + bw - 20), by + bh if sy > by + bh else by)
        if by <= sy <= by + bh:
            p0 = (bx if sx < bx else bx + bw, by + bh / 2)
        v = np.array([sx - p0[0], sy - p0[1]])
        L = np.linalg.norm(v)
        if L > 40:
            v = v / L
            p1 = (sx - v[0] * opt.get("gap", 26), sy - v[1] * opt.get("gap", 26))
            gfx.draw_arrow(cv, p0, p1, _line_color(style), ease_out(clamp01((u - 0.15) / 0.85)), al, bend=0.15, thick=5)
        if opt.get("ring", True):
            pulse = 0.5 + 0.5 * math.sin((t - a) * 8)
            draw_ring(cv, (sx, sy), 14 + 6 * pulse, _line_color(style), 3, al * 0.85)


# ================================================================ 팝업 텍스트
POP_STYLES = {
    "impact": dict(size=118, fill=(255, 214, 64), fill2=(255, 120, 40), stroke=(36, 12, 0), sw=10, angle=-7, anim="punch"),
    "danger": dict(size=110, fill=(255, 76, 64), fill2=(255, 214, 64), stroke=(30, 0, 0), sw=10, angle=6, anim="punch"),
    "cool": dict(size=104, fill=(110, 226, 255), fill2=(255, 255, 255), stroke=(0, 22, 44), sw=9, angle=-4, anim="punch"),
    "info": dict(size=62, fill=(255, 255, 255), fill2=(255, 214, 64), stroke=(10, 12, 20), sw=7, angle=0, anim="slide"),
    "funny": dict(size=92, fill=(255, 255, 255), fill2=(255, 230, 90), stroke=(236, 60, 150), sw=10, angle=-5, anim="bounce"),
    "small": dict(size=52, fill=(255, 214, 64), fill2=(255, 255, 255), stroke=(20, 10, 0), sw=6, angle=-3, anim="bounce"),
    "party": dict(size=104, fill=(255, 104, 160), fill2=(255, 206, 64), stroke=(255, 255, 255), sw=11, angle=-4, anim="bounce"),
    "sweet": dict(size=64, fill=(255, 255, 255), fill2=(255, 150, 190), stroke=(214, 70, 120), sw=7, angle=-3, anim="bounce"),
    "count": dict(size=230, fill=(255, 255, 255), fill2=(255, 206, 64), stroke=(255, 94, 140), sw=14, angle=0, anim="punch"),
}


@lru_cache(None)
def pop_sprite(text, style):
    st = POP_STYLES[style]
    size, sw = st["size"], st["sw"]
    segs = parse_rich(text, st["fill"], st["fill2"])
    f = font(gfx.FONT_B, size)
    runs = [(e, r, col) for s, col in segs for e, r in gfx._runs(s)]
    tw = sum(emoji_img(r, size)[0].width if e else f.getlength(r) for e, r, _ in runs)
    w, h = int(tw + sw * 2 + 8), int(size * 1.45 + sw * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x, base = sw + 4, sw + size * 1.08
    for e, r, col in runs:
        if e:
            em, asc = emoji_img(r, size)
            img.alpha_composite(em, (int(x), int(base - asc)))
            x += em.width
        else:
            d.text((x, base), r, font=f, anchor="ls", fill=col, stroke_width=sw, stroke_fill=st["stroke"])
            x += f.getlength(r)
    if st["angle"]:
        img = img.rotate(st["angle"], resample=Image.BICUBIC, expand=True)
    img, pad = with_shadow(img, radius=14, offset=(0, 10), opacity=0.6)
    return Sprite(img, pad)


def layer_pops(cv, view, t, ts):
    for a, b, where, text, style in TL.pops:
        w = window(t, a, b, 0.12, 0.25)
        if not w:
            continue
        al, _ = w
        st = POP_STYLES[style]
        if where == "center":
            x, y = W / 2, H * 0.42
        elif isinstance(where, dict):
            x, y = where["x"], where["y"]
        else:
            x, y = view.s(where.pt(ts))
            y -= 70
        sp = pop_sprite(text, style)
        bw, bh = sp.body
        x = min(max(x, bw / 2 + 20), W - bw / 2 - 20)
        y = min(max(y, bh / 2 + 20), H - bh / 2 - 130)
        u = t - a
        sc, dx, dy = 1.0, 0.0, 0.0
        if st["anim"] == "punch":
            sc = 1 + 1.3 * (1 - ease_out(clamp01(u / 0.2)))
            if u < 0.35:
                j = 9 * (1 - u / 0.35)
                dx, dy = j * math.sin(u * 90), j * math.cos(u * 77)
            sc *= 1 + 0.04 * clamp01((u - 0.2) / max(0.01, b - a))
        elif st["anim"] == "slide":
            dy = 40 * (1 - ease_out(clamp01(u / 0.35)))
        else:  # bounce
            sc = 0.3 + 0.7 * ease_back(clamp01(u / 0.35), 2.6)
            dy = -6 * math.sin(u * 7)
        out = clamp01((b - t) / 0.25)
        if out < 1:
            sc *= 1 + 0.15 * (1 - out)
        cv.sprite(sp, x + dx, y + dy, al, sc)


# ================================================================ 스티커
@lru_cache(None)
def sticker_sprite(emo, size):
    im, _ = emoji_img(emo, size)
    im, pad = with_shadow(im, radius=8, offset=(0, 6), opacity=0.5, pad=20)
    return Sprite(im, pad)


def layer_stickers(cv, view, t, ts):
    for a, b, tgt, emo, opt in TL.stickers:
        w = window(t, a, b, 0.3, 0.25)
        if not w:
            continue
        al, u = w
        x, y = view.s(tgt.pt(ts))
        x += opt.get("dx", 0)
        y += opt.get("dy", -90)
        motion = opt.get("motion", "bob")
        sc = 0.3 + 0.7 * ease_back(u, 2.4)
        if motion == "bob":
            y += 8 * math.sin((t - a) * 5)
        elif motion == "pulse":
            sc *= 1 + 0.08 * math.sin((t - a) * 9)
        cv.sprite(sticker_sprite(emo, opt.get("size", 96)), x, y, al, sc)


# ================================================================ 속도·정지 배지
def layer_badges(cv, t):
    items = [(a, b, label) for a, b, _, label in TL.speed_labels if label] + [(a, b, label) for a, b, label, _ in TL.freezes if label]
    for a, b, label in items:
        w = window(t, a, b, 0.2, 0.2)
        if not w:
            continue
        al, u = w
        sp = pill_sprite(label, size=30, fg=gfx.WHITE, bg=(16, 18, 27, 225), padx=22, pady=10, border=(255, 255, 255, 60))
        cv.sprite(sp, 40 - 40 * (1 - ease_out(u)), 60, al, anchor=(0, 0))


# ================================================================ 파티클 (PARTICLES)
# (t0, t1, 종류, dict(at="@트랙" | (x, y) 원본 좌표 | "screen", burst=개수 | rate=초당 개수, ...))
# 종류: confetti(꽃가루) hearts(하트) sparkle(반짝이) bokeh(빛망울) notes(음표) stars(별) snow(눈)
#       petals(벚꽃잎) leaves(단풍잎) fireflies(반딧불) — 자연·여행·광고용. petals/leaves 는 위에서 흩날리며 내려온다
# 위치는 매 프레임 '발생 지점(트랙) + 이동량' — 프레임마다 독립 계산이라 병렬 렌더링에서도 결과가 같다.
PCOLORS = [(255, 94, 120), (255, 196, 61), (90, 200, 250), (130, 230, 140), (190, 120, 255), (255, 150, 60), (255, 255, 255)]
PKIND = {
    #            속도(px/s)     중력   수명       크기       퍼짐(rad)   위쪽 기준
    "confetti": dict(v=(700, 1300), g=900, life=(1.8, 2.8), size=(12, 22), spread=1.1, drag=1.6),
    "hearts": dict(v=(60, 140), g=-40, life=(2.0, 3.2), size=(30, 54), spread=0.6, drag=0.3),
    "sparkle": dict(v=(10, 60), g=0, life=(0.5, 1.1), size=(16, 34), spread=3.14, drag=0.5),
    "bokeh": dict(v=(8, 30), g=-6, life=(3.0, 5.0), size=(40, 110), spread=3.14, drag=0.0),
    "notes": dict(v=(70, 130), g=-30, life=(1.6, 2.6), size=(34, 50), spread=0.7, drag=0.2),
    "stars": dict(v=(200, 500), g=300, life=(0.9, 1.5), size=(24, 40), spread=3.14, drag=1.2),
    "snow": dict(v=(30, 70), g=40, life=(4.0, 6.0), size=(8, 16), spread=0.4, drag=0.0),
    "petals": dict(v=(50, 120), g=14, life=(5.0, 8.0), size=(16, 28), spread=0.5, drag=0.25),
    "leaves": dict(v=(60, 130), g=22, life=(4.5, 7.0), size=(26, 44), spread=0.5, drag=0.25),
    "fireflies": dict(v=(6, 26), g=-5, life=(2.5, 4.5), size=(14, 26), spread=3.14, drag=0.0),
}
P_ANGLE = {"petals": 105, "leaves": 100, "snow": 90}  # 기본 발사 방향(도): 아래로 흩날림
P_TOP = ("confetti", "snow", "petals", "leaves")  # 화면 위쪽 가장자리에서 생기는 종류
PETAL_COLS = [(255, 196, 210), (248, 170, 192), (255, 220, 228), (240, 150, 178), (252, 186, 200)]
LEAF_COLS = [(206, 58, 34), (228, 96, 30), (240, 152, 42), (184, 40, 30), (236, 120, 40)]


@lru_cache(None)
def _p_leaf(kind, ci, ai, size):
    """벚꽃잎(끝이 갈라진 타원) / 단풍잎(다섯 갈래). ai: 회전 단계(16), 뒤집힘 느낌으로 납작해진다."""
    ss = 3
    s = size * 2 * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = ai / 16 * 2 * math.pi
    sq = abs(math.cos(a * 1.3)) * 0.75 + 0.25
    cx = cy = s / 2
    R = size * ss * 0.5
    if kind == "petals":
        col = PETAL_COLS[ci % len(PETAL_COLS)]
        pts = []
        for k in range(48):
            th = k / 48 * 2 * math.pi
            r = R * (1 - 0.28 * max(0, math.cos(th)) ** 12)  # 끝의 홈
            pts.append((r * math.cos(th), r * 0.62 * math.sin(th)))
    else:
        col = LEAF_COLS[ci % len(LEAF_COLS)]
        pts = []
        for k in range(90):
            th = k / 90 * 2 * math.pi
            lobe = abs(math.cos(2.5 * (th + math.pi / 2))) ** 0.7
            r = R * (0.42 + 0.58 * lobe) * (0.75 if math.sin(th) > 0.6 else 1)
            pts.append((r * math.cos(th), r * math.sin(th)))
    pts = [(cx + x * math.cos(a) - y * sq * math.sin(a), cy + x * math.sin(a) + y * sq * math.cos(a)) for x, y in pts]
    d.polygon(pts, fill=(*col, 235))
    if kind == "leaves":
        d.line([(cx, cy), (cx + R * 0.9 * math.sin(a), cy + R * 0.9 * math.cos(a) * sq)], fill=(120, 40, 20, 200), width=ss * 2)
    img = img.resize((size * 2, size * 2), Image.LANCZOS)
    return Sprite(img, 0)


@lru_cache(None)
def _p_confetti(ci, ai, size):
    c = PCOLORS[ci]
    w, h = size, int(size * 0.55)
    a = ai / 8 * math.pi
    sq = abs(math.cos(a * 1.7)) * 0.85 + 0.15  # 뒤집히며 납작해지는 느낌
    img = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size
    pts = [(-w / 2, -h / 2 * sq), (w / 2, -h / 2 * sq), (w / 2, h / 2 * sq), (-w / 2, h / 2 * sq)]
    pts = [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)) for x, y in pts]
    d.polygon(pts, fill=(*c, 255))
    return Sprite(img, 0)


@lru_cache(None)
def _p_glow(kind, ci, size):
    c = {"sparkle": (255, 244, 200), "fireflies": (255, 232, 140), "snow": (255, 255, 255)}.get(kind, PCOLORS[ci])
    s = size * 3
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    dx, dy = (x - s / 2) / size, (y - s / 2) / size
    r = np.sqrt(dx ** 2 + dy ** 2)
    if kind == "bokeh":
        a = np.clip((0.5 - r) / 0.12, 0, 1) * 0.28 + np.clip((0.5 - r) / 0.03, 0, 1) * np.clip((r - 0.42) / 0.08, 0, 1) * 0.12
    elif kind == "snow":
        a = np.clip((0.5 - r) / 0.25, 0, 1) * 0.9
    elif kind == "fireflies":
        a = np.clip(np.exp(-r * r * 60) * 1.2 + np.exp(-r * r * 7) * 0.35, 0, 1)
    else:  # sparkle: 4갈래 별 + 글로우
        star = np.exp(-np.abs(dx) * 14) * np.exp(-np.abs(dy) * 1.6) + np.exp(-np.abs(dy) * 14) * np.exp(-np.abs(dx) * 1.6)
        a = np.clip(star * 1.2 + np.exp(-r * r * 18) * 0.8, 0, 1)
    arr = np.zeros((s, s, 4), np.float32)
    arr[..., 3] = a
    for k in range(3):
        arr[..., k] = c[k] / 255 * a
    sp = Sprite.__new__(Sprite)
    sp.arr, sp.h, sp.w, sp.pad = arr, s, s, size
    return sp


EMO = {"hearts": ["💖", "💕", "❤️", "💗", "🧡"], "notes": ["🎵", "🎶"], "stars": ["⭐", "🌟", "✨"]}


class _Emitter:
    def __init__(self, t0, t1, kind, opt, seed):
        self.t0, self.t1, self.kind, self.opt = t0, t1, kind, opt
        self.at = opt.get("at", "screen")
        p = dict(PKIND[kind])
        p.update({k: opt[k] for k in ("v", "g", "life", "size", "spread", "drag") if k in opt})
        r = np.random.default_rng(seed)
        if opt.get("burst"):
            n = int(opt["burst"])
            spawn = t0 + r.random(n) * opt.get("burst_dur", 0.12)
        else:
            rate = opt.get("rate", 8)
            n = max(1, int((t1 - t0) * rate))
            spawn = np.sort(t0 + r.random(n) * max(0.01, t1 - t0))
        ang0 = math.radians(opt.get("angle", P_ANGLE.get(kind, -90)))  # 기본: 위쪽으로 (흩날리는 종류는 아래로)
        self.spawn = spawn
        self.life = r.uniform(*p["life"], n)
        sp = r.uniform(*p["v"], n)
        ang = ang0 + (r.random(n) - 0.5) * 2 * p["spread"]
        self.vx, self.vy = np.cos(ang) * sp, np.sin(ang) * sp
        self.g, self.drag = p["g"], p["drag"]
        self.size = r.uniform(*p["size"], n).astype(int)
        self.col = r.integers(0, len(PCOLORS) - (0 if kind != "confetti" else 1), n)
        if opt.get("palette"):  # PCOLORS 번호 목록 (예: [6] = 흰색 물보라)
            self.col = r.choice(opt["palette"], n)
        self.rot0 = r.integers(0, 16, n)
        self.vrot = r.uniform(4, 14, n) * r.choice([-1, 1], n)
        self.emo = r.integers(0, 5, n)
        self.phase = r.random(n) * 6.28
        area = opt.get("area")  # "screen" 모드: 발생 영역 (x0, y0, x1, y1) 캔버스
        if self.at == "screen":
            a = area or ((0, H * 0.2, W, H) if kind in ("bokeh",) else (0, -40, W, -10) if kind in P_TOP else (0, 0, W, H))
            self.ox = r.uniform(a[0], a[2], n)
            self.oy = r.uniform(a[1], a[3], n)
        else:
            j = opt.get("jitter", 30)
            self.ox = (r.random(n) - 0.5) * 2 * j
            self.oy = (r.random(n) - 0.5) * 2 * j * 0.6

    def draw(self, cv, view, t, ts):
        if t < self.t0 or t > self.t1 + self.life.max():
            return
        if self.at == "screen":
            bx = by = 0.0
        elif isinstance(self.at, str):
            bx, by = view.s(TL.target(self.at).pt(ts))
        else:
            bx, by = view.s(TL.P(self.at))
        age = t - self.spawn
        m = (age >= 0) & (age <= self.life)
        fade_all = self.opt.get("alpha", 1.0)
        for i in np.nonzero(m)[0]:
            a, L = age[i], self.life[i]
            if self.drag:
                k = (1 - math.exp(-self.drag * a)) / self.drag
            else:
                k = a
            x = bx + self.ox[i] + self.vx[i] * k
            y = by + self.oy[i] + self.vy[i] * k + 0.5 * self.g * a * a
            u = a / L
            al = min(1.0, a / 0.12) * (1 - max(0.0, (u - 0.7) / 0.3)) * fade_all
            if self.kind == "confetti":
                x += 18 * math.sin(a * 5 + self.phase[i])
                ai = int(self.rot0[i] + self.vrot[i] * a) % 16
                cv.sprite(_p_confetti(int(self.col[i]), ai, int(self.size[i])), x, y, al)
            elif self.kind in ("petals", "leaves"):
                x += 46 * math.sin(a * 1.1 + self.phase[i]) + 18 * math.sin(a * 2.7 + self.phase[i] * 2)
                ai = int(self.rot0[i] + self.vrot[i] * 0.35 * a) % 16
                cv.sprite(_p_leaf(self.kind, int(self.col[i]), ai, int(self.size[i])), x, y, al)
            elif self.kind in ("sparkle", "bokeh", "snow", "fireflies"):
                tw = 0.5 + 0.5 * math.sin(a * (12 if self.kind == "sparkle" else 4) + self.phase[i]) \
                    if self.kind in ("sparkle", "fireflies") else 1.0
                sc = (0.4 + 0.6 * math.sin(math.pi * min(1, u))) if self.kind == "sparkle" else 1.0
                if self.kind == "snow":
                    x += 20 * math.sin(a * 1.5 + self.phase[i])
                if self.kind == "fireflies":
                    x += 28 * math.sin(a * 0.9 + self.phase[i])
                    y += 16 * math.sin(a * 1.4 + self.phase[i] * 2)
                    al *= min(1.0, (1 - u) * 3)
                cv.sprite(_p_glow(self.kind, int(self.col[i]), int(self.size[i])), x, y, al * (0.55 + 0.45 * tw), max(0.2, sc))
            else:
                x += 14 * math.sin(a * 3 + self.phase[i])
                emo = EMO[self.kind][int(self.emo[i]) % len(EMO[self.kind])]
                sc = 0.5 + 0.5 * ease_back(min(1, a / 0.35))
                cv.sprite(sticker_sprite(emo, int(self.size[i] // 4 * 4)), x, y, al, sc)


def layer_particles(cv, view, t, ts):
    for e in TL._emitters:
        e.draw(cv, view, t, ts)


# ================================================================ 폴라로이드 사진 (PHOTOS)
# (t0, t1, 원본 시각, (x0, y0, x1, y1) 원본 영역, 캡션[, dict(pos=(x, y) 캔버스, w=560, angle=-5, enter="drop|pop")])
def _grab(src, ts, rect):
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(ts * cap.get(cv2.CAP_PROP_FPS))))
    ok, f = cap.read()
    cap.release()
    x0, y0, x1, y1 = [int(v) for v in rect]
    return f[y0:y1, x0:x1] if ok else None


def _polaroid(img_bgr, caption, w, angle):
    ih = int(w * img_bgr.shape[0] / img_bgr.shape[1])
    pad, bottom = int(w * 0.055), int(w * 0.2)
    card = Image.new("RGBA", (w + pad * 2, ih + pad + bottom), (252, 250, 245, 255))
    photo = Image.fromarray(cv2.cvtColor(cv2.resize(img_bgr, (w, ih), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    card.paste(photo, (pad, pad))
    d = ImageDraw.Draw(card)
    d.rectangle([pad, pad, pad + w - 1, pad + ih - 1], outline=(0, 0, 0, 40), width=1)
    if caption:
        segs = parse_rich(caption, (60, 56, 70), gfx.ACCENT)
        size = int(bottom * 0.36)
        while gfx.rich_width(segs, size) > w and size > 14:
            size -= 2
        gfx.draw_rich(d, (card.width - gfx.rich_width(segs, size)) / 2, ih + pad + bottom * 0.62, segs, size)
    if angle:
        card = card.rotate(angle, resample=Image.BICUBIC, expand=True)
    card, p = with_shadow(card, radius=18, offset=(0, 14), opacity=0.55)
    return Sprite(card, p)


def layer_photos(cv, t):
    for (a, b, *_), sp, opt in TL._photos:
        w = window(t, a, b, 0.5, 0.35)
        if not w:
            continue
        al, u = w
        x, y = opt.get("pos", (W / 2, H / 2))
        if opt.get("enter", "drop") == "drop":
            y -= 140 * (1 - ease_out(u))
            sc = 1.25 - 0.25 * ease_back(u)
        else:
            sc = 0.3 + 0.7 * ease_back(u)
        cv.sprite(sp, x, y, al, sc)


def setup(tl):
    global TL
    TL = tl
    tl._emitters = [_Emitter(a, b, kind, opt, 11 + i * 17) for i, (a, b, kind, opt) in enumerate(tl.particles)]
    tl._photos = []
    for ph in tl.photos:
        a, b, src_t, rect, caption, opt = ph
        img = _grab(tl.src, src_t, rect)
        if img is not None:
            tl._photos.append((ph, _polaroid(img, caption, opt.get("w", 560), opt.get("angle", -5)), opt))
