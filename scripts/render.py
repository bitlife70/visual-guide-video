"""프레임 합성 엔진: 카메라 줌 → 스포트라이트 → 오버레이 레이어(하이라이트·클릭·풍선·카드·HUD·자막) → 인트로/아웃트로."""
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

import fx
import gfx
import promo
from gfx import (CHIP_W, Canvas, Sprite, card_sprite, chip_sprite, clamp01, dim_outside, draw_arrow, draw_dot,
                 draw_rich, draw_ring, draw_rrect, ease_back, ease_io, ease_out, font, parse_rich, pill_sprite,
                 rich_width, subtitle_sprite, window, with_shadow)

W, H = gfx.W, gfx.H
WHITE, INK = gfx.WHITE, gfx.INK
TL = None  # setup() 에서 주입


# ================================================================ camera
def _rect(cx, cy, z):
    """중심·배율 → 뷰 사각형 (x0, y0, 너비). 실제 영상 영역(TL.content) 안에 머물도록 고정, 영역보다 크면 가운데 정렬."""
    vw, vh = W / z, H / z
    x0c, y0c, x1c, y1c = TL.content
    x = min(max(cx - vw / 2, x0c), x1c - vw) if vw <= x1c - x0c else (x0c + x1c - vw) / 2
    y = min(max(cy - vh / 2, y0c), y1c - vh) if vh <= y1c - y0c else (y0c + y1c - vh) / 2
    return (x, y, vw)


def _shot_rect(sh, ts):
    if sh["target"] is not None:
        cx, cy = sh["target"].pt(ts)
        cx, cy = cx + sh["off"][0], cy + sh["off"][1]
    else:
        cx, cy = sh["c"]
    return _rect(cx, cy, sh["z"])


def camera(t, ts):
    shots = TL.shots
    i = 0
    for k, sh in enumerate(shots):
        if sh["t"] <= t:
            i = k
    sh = shots[i]
    cur = _shot_rect(sh, ts)
    if i > 0 and sh["dur"] > 0 and t < sh["t"] + sh["dur"]:
        fr = _shot_rect(shots[i - 1], ts)
        e = ease_io((t - sh["t"]) / sh["dur"])
        vw = math.exp(math.log(fr[2]) + (math.log(cur[2]) - math.log(fr[2])) * e)
        return (fr[0] + (cur[0] - fr[0]) * e, fr[1] + (cur[1] - fr[1]) * e, vw)
    return cur


class View:
    def __init__(self, t, ts=None):
        ts = TL.remap.src(t) if ts is None else ts
        self.x0, self.y0, vw = camera(t, ts)
        self.z = W / vw
        dx, dy, zm = fx.camera_offset(t)
        if dx or dy or zm != 1:
            zm *= 1 + 2.2 * (abs(dx) + abs(dy)) / W  # 흔들림 가장자리 감추기
            cx, cy = self.x0 + vw / 2, self.y0 + vw * H / W / 2
            self.z *= zm
            self.x0 = cx - W / self.z / 2 - dx / self.z
            self.y0 = cy - H / self.z / 2 - dy / self.z

    def s(self, p):
        return ((p[0] - self.x0) * self.z, (p[1] - self.y0) * self.z)

    def rect(self, r):
        a, b = self.s(r[:2]), self.s(r[2:])
        return (a[0], a[1], b[0], b[1])

    def warp(self, frame):
        if abs(self.z - 1) < 1e-4 and abs(self.x0) < 0.01 and abs(self.y0) < 0.01:
            return frame
        M = np.float32([[self.z, 0, -self.x0 * self.z], [0, self.z, -self.y0 * self.z]])
        out = cv2.warpAffine(frame, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if self.z > 1.15:  # 확대 시 살짝 샤프닝
            k = min(0.6, (self.z - 1) * 0.45)
            blur = cv2.GaussianBlur(out, (0, 0), 1.2)
            out = cv2.addWeighted(out, 1 + k, blur, -k, 0)
        return out


def letterbox(frame):
    """원본 프레임을 디자인 캔버스로. 여백은 BACKDROP: 검정 / 흐리게 확대한 같은 프레임(세로 쇼츠) / 단색."""
    h, w = frame.shape[:2]
    if (w, h) == (W, H):
        return frame
    s = TL.scale
    nw, nh = int(round(w * s)), int(round(h * s))
    r = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    bd = TL.backdrop
    tint = None
    if isinstance(bd, dict):  # dict(kind="blur", tint=(r, g, b), amount=0.45)
        tint, amt, bd = bd.get("tint"), bd.get("amount", 0.45), bd.get("kind", "blur")
    if bd == "blur":
        k = max(W / w, H / h)
        small = cv2.resize(frame, (max(1, int(w * k / 8)), max(1, int(h * k / 8))), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), 6)
        big = cv2.resize(small, (int(w * k), int(h * k)), interpolation=cv2.INTER_LINEAR)
        bx, by = (big.shape[1] - W) // 2, (big.shape[0] - H) // 2
        out = big[by:by + H, bx:bx + W].astype(np.float32)
        if tint is not None:
            out = out * (1 - amt) + np.array(tint[::-1], np.float32) * amt
        else:
            out = out * 0.82 + 255 * 0.08
        out = out.astype(np.uint8)
    elif isinstance(bd, (tuple, list)):
        out = np.empty((H, W, 3), np.uint8)
        out[:] = bd[::-1]
    else:
        out = np.zeros((H, W, 3), np.uint8)
    ox, oy = (W - nw) // 2, (H - nh) // 2
    out[oy:oy + nh, ox:ox + nw] = r
    return out


# ================================================================ static sprites
class S:
    pass


def _hud_sprites(hud):
    items = hud["items"]
    w = 400
    h = 94 + len(items) * 46 + 14
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 20, fill=(14, 16, 24, 222), outline=(255, 255, 255, 40), width=2)
    d.ellipse([20, 22, 34, 36], fill=gfx.ACCENT)
    draw_rich(d, 44, 38, [(hud.get("title", "세션 모니터"), WHITE)], 23)
    badge = hud.get("badge", f"{len(items)} LIVE")
    if badge:
        bw = rich_width([(badge, gfx.GREEN)], 18)
        draw_rich(d, w - 20 - bw, 38, [(badge, gfx.GREEN)], 18)
    d.line([18, 84, w - 18, 84], fill=(255, 255, 255, 34), width=2)
    panel, pad = with_shadow(panel, radius=16)
    rows = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(rows)
    active = []
    for i, (emo, name) in enumerate(items):
        y = 94 + i * 46 + 32
        draw_rich(d, 24, y, [(emo, WHITE)], 26)
        draw_rich(d, 66, y, [(name, (168, 175, 192))], 23, bold=False)
        a = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_rich(ImageDraw.Draw(a), 66, y, [(name, WHITE)], 23, bold=True)
        active.append(Sprite(a))
    steps = {}
    for _, label in hud.get("steps", []):
        s = Image.new("RGBA", (w, 34), (0, 0, 0, 0))
        draw_rich(ImageDraw.Draw(s), 22, 26, [(label, gfx.ACCENT)], 20)
        steps[label] = Sprite(s)
    # 미니 HUD (줌인 시)
    mh = 16 + len(items) * 54 + 10
    mp = Image.new("RGBA", (72, mh), (0, 0, 0, 0))
    ImageDraw.Draw(mp).rounded_rectangle([0, 0, 71, mh - 1], 18, fill=(14, 16, 24, 225), outline=(255, 255, 255, 40), width=2)
    mp, mpad = with_shadow(mp, radius=12)
    mi = Image.new("RGBA", (72, mh), (0, 0, 0, 0))
    d = ImageDraw.Draw(mi)
    for i, (emo, _) in enumerate(items):
        draw_rich(d, 19, 16 + i * 54 + 38, [(emo, WHITE)], 34)
    return Sprite(panel, pad), Sprite(rows), active, steps, Sprite(mp, mpad), Sprite(mi)


def _title_sprites(tt):
    big = Image.new("RGBA", (1700, 170), (0, 0, 0, 0))
    segs = parse_rich(tt.get("title", ""), WHITE, gfx.ACCENT)
    size = 124
    while rich_width(segs, size) > 1650 and size > 60:
        size -= 6
    draw_rich(ImageDraw.Draw(big), (1700 - rich_width(segs, size)) / 2, 135, segs, size)
    big, bp = with_shadow(big, radius=24, opacity=0.8)
    sub = Image.new("RGBA", (1700, 80), (0, 0, 0, 0))
    segs = parse_rich(tt.get("subtitle", ""), (226, 230, 240), gfx.ACCENT)
    draw_rich(ImageDraw.Draw(sub), (1700 - rich_width(segs, 48)) / 2, 60, segs, 48)
    sub, sp = with_shadow(sub, radius=16, opacity=0.8)
    tokens = []
    for emo, name in tt.get("tokens", []):
        im = Image.new("RGBA", (190, 190), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([40, 6, 150, 116], fill=(18, 20, 30, 240), outline=gfx.ACCENT, width=4)
        ew = rich_width([(emo, WHITE)], 62)
        draw_rich(d, 95 - ew / 2, 82, [(emo, WHITE)], 62)
        tw = rich_width([(name, WHITE)], 24)
        draw_rich(d, 95 - tw / 2, 158, [(name, (230, 233, 242))], 24)
        im, p = with_shadow(im, radius=12)
        tokens.append(Sprite(im, p))
    chip = pill_sprite(tt["chip"], size=24, fg=INK, bg=gfx.ACCENT, padx=22, pady=8) if tt.get("chip") else None
    return Sprite(big, bp), Sprite(sub, sp), tokens, chip


def _outro_sprites(oo):
    big = Image.new("RGBA", (1800, 120), (0, 0, 0, 0))
    segs = parse_rich(oo.get("title", ""), WHITE, gfx.ACCENT)
    size = 74
    while rich_width(segs, size) > 1760 and size > 40:
        size -= 4
    draw_rich(ImageDraw.Draw(big), (1800 - rich_width(segs, size)) / 2, 92, segs, size)
    big, p = with_shadow(big, radius=20, opacity=0.8)
    stats = []
    for emo, a, b in oo.get("stats", []):
        im = Image.new("RGBA", (430, 170), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, 429, 169], 26, fill=(16, 18, 27, 240), outline=(255, 255, 255, 50), width=2)
        d.rounded_rectangle([0, 0, 429, 10], 5, fill=gfx.ACCENT)
        draw_rich(d, 34, 108, [(emo, WHITE)], 64)
        draw_rich(d, 128, 82, [(a, WHITE)], 38)
        draw_rich(d, 128, 128, [(b, (180, 188, 205))], 30, bold=False)
        im, q = with_shadow(im, radius=18)
        stats.append(Sprite(im, q))
    chip = pill_sprite(oo["chip"], size=28, fg=INK, bg=gfx.ACCENT, padx=24, pady=10) if oo.get("chip") else None
    foot = pill_sprite(oo["footer"], size=24, fg=(200, 206, 220), bg=(16, 18, 27, 220), padx=24, pady=8) if oo.get("footer") else None
    return Sprite(big, p), stats, chip, foot


def setup(tl):
    global TL
    TL = tl
    gfx.set_theme(tl.theme)
    fx.setup(tl)
    promo.setup(tl)
    if tl.hud:
        S.hud = _hud_sprites(tl.hud)
    if tl.title:
        S.title = _title_sprites(tl.title)
    if tl.outro:
        S.outro = _outro_sprites(tl.outro)
    if tl.flow and tl.flow.get("title"):
        S.flow_title = pill_sprite(tl.flow["title"], size=28, fg=INK, bg=gfx.CYAN, padx=24, pady=10)


# ================================================================ helpers
def _clamp_box(cx, cy, bw, bh, ax, ay, m=24):
    x0 = cx - ax * bw
    y0 = cy - ay * bh
    x0 = min(max(x0, 100), W - m - bw)  # 좌측 100px 은 미니 HUD 자리
    y0 = min(max(y0, m + 50), H - 150 - bh)
    return x0 + ax * bw, y0 + ay * bh


# ================================================================ layers
def layer_highlights(cv, view, t, frame, ts):
    active = []
    for t0, t1, tgt, label, col, *opt in TL.highlights:
        w = window(t, t0, t1, 0.3, 0.25)
        if not w:
            continue
        a, u = w
        r = view.rect(tgt.rect(ts))
        g = 1 - ease_out(u)
        r = (r[0] - 14 * g, r[1] - 14 * g, r[2] + 14 * g, r[3] + 14 * g)
        place = opt[0] if opt else "auto"  # "right|nodim" 처럼 | 로 옵션 추가
        active.append((a, r, label, gfx.COLORS[col], t0, place.split("|")[0], "nodim" not in place))
    dims = [x for x in active if x[6]]
    if dims:
        a = max(x[0] for x in dims)
        u = (min(x[1][0] for x in dims), min(x[1][1] for x in dims),
             max(x[1][2] for x in dims), max(x[1][3] for x in dims))
        frame = dim_outside(frame, (u[0] - 10, u[1] - 8, u[2] + 10, u[3] + 8), 0.42 * a)
    for a, r, label, col, t0, place, _ in active:
        pulse = 0.5 + 0.5 * math.sin((t - t0) * 7)
        draw_rrect(cv, r, col, thick=4, r=12, alpha=a, glow=8 + 3 * pulse)
        if not label:
            continue
        sp = pill_sprite(label, size=28, fg=INK, bg=col, padx=18, pady=8)
        bw, bh = sp.body
        sc = 0.85 + 0.15 * ease_back(min(1, (t - t0) / 0.3))
        if place == "right":
            cx, cy = _clamp_box(r[2] + 70, (r[1] + r[3]) / 2, bw, bh, 0, 0.5)
            cv.sprite(sp, cx, cy, a, sc, anchor=(0, 0.5))
            draw_arrow(cv, (cx - 6, cy), (r[2] + 8, cy), col, ease_out(clamp01((t - t0) / 0.4)), a, bend=0, thick=5)
        elif place == "above-right":
            cx, cy = _clamp_box(r[2], r[1] - 8, bw, bh, 1, 1)
            cv.sprite(sp, cx, cy, a, sc, anchor=(1, 1))
        elif place == "below" or r[1] <= 130:
            cx, cy = _clamp_box(r[0], r[3] + 12, bw, bh, 0, 0)
            cv.sprite(sp, cx, cy, a, sc, anchor=(0, 0))
        else:
            cx, cy = _clamp_box(r[0], r[1] - 12, bw, bh, 0, 1)
            cv.sprite(sp, cx, cy, a, sc, anchor=(0, 1))
    return frame


def layer_clicks(cv, view, t, frame):
    for tc, pos, label in TL.clicks:
        sx, sy = view.s(pos)
        w = window(t, tc - 0.6, tc + 0.4, 0.25, 0.3)
        if w:  # 스포트라이트
            frame = dim_outside(frame, (sx - 150, sy - 46, sx + 150, sy + 46), 0.5 * w[0], feather=34)
        if tc - 0.55 <= t < tc:  # 타깃 펄스
            p = (t - (tc - 0.55)) / 0.55
            draw_ring(cv, (sx, sy), 44 - 14 * ease_out(p), gfx.ACCENT, 4, 0.9 * clamp01(p * 3))
        if tc <= t < tc + 0.7:  # 리플
            p = (t - tc) / 0.7
            for k, delay in enumerate((0, 0.18)):
                q = clamp01((p - delay) / (1 - delay))
                if q > 0:
                    draw_ring(cv, (sx, sy), 12 + 95 * ease_out(q), WHITE if k else gfx.ACCENT, 7 * (1 - q) + 1, (1 - q) * 0.95)
            draw_dot(cv, (sx, sy), 14 * (1 - p), gfx.ACCENT, 1 - p, glow=6)
        if not label:
            continue
        w = window(t, tc - 0.42, tc + 1.15, 0.28, 0.3)
        if w:  # 풍선 + 화살표
            a, u = w
            sp = pill_sprite(label, size=34, padx=26, pady=14)
            bw, bh = sp.body
            right = sx < W * 0.55
            down = sy < H * 0.5
            bx = sx + 150 if right else sx - 150 - bw
            by = sy + 120 if down else sy - 120 - bh
            bx = min(max(bx, 24), W - 24 - bw)
            by = min(max(by, 74), H - 160 - bh)
            cv.sprite(sp, bx + bw / 2, by + bh / 2, a, 0.6 + 0.4 * ease_back(u))
            p0 = (bx if right else bx + bw, by + bh / 2)
            v = np.array([sx - p0[0], sy - p0[1]])
            v = v / (np.linalg.norm(v) + 1e-6)
            p1 = (sx - v[0] * 30, sy - v[1] * 30)
            bend = 0.22 if (right == down) else -0.22
            draw_arrow(cv, p0, p1, gfx.ACCENT, ease_out(clamp01((u - 0.2) / 0.8)), a, bend=bend)
    return frame


def layer_links(cv, view, t):
    for t0, t1, src, tab, label in TL.links:
        w = window(t, t0, t1, 0.25, 0.25)
        if not w:
            continue
        a, u = w
        r = view.rect(tab)
        tc = ((r[0] + r[2]) / 2, r[3] + 8)
        draw_arrow(cv, view.s(src), tc, gfx.CYAN, ease_out(clamp01((t - t0) / 0.45)), a, bend=-0.18, thick=5)
        pulse = 0.5 + 0.5 * math.sin((t - t0) * 9)
        if t - t0 > 0.3:
            k = clamp01((t - t0 - 0.3) / 0.2)
            draw_rrect(cv, (r[0] + 2, r[1] + 2, r[2] - 2, r[3] - 2), gfx.CYAN, 4, 10, a * k, glow=8 + 4 * pulse)
            if label:
                sp = pill_sprite("✨ " + label, size=26, fg=INK, bg=gfx.CYAN, padx=18, pady=7)
                cv.sprite(sp, (r[0] + r[2]) / 2, r[3] + 74, a * k, 0.8 + 0.2 * ease_back(k))


def layer_cards(cv, t):
    x, y = TL.card_pos
    for t0, t1, emo, title, lines, badge in TL.cards:
        w = window(t, t0, t1, 0.4, 0.3)
        if not w:
            continue
        a, u = w
        sp = card_sprite(emo, title, tuple(lines), badge)
        cv.sprite(sp, x + 90 * (1 - ease_out(u)), y, a, anchor=(1, 0))


def layer_flow(cv, t):
    fl = TL.flow
    if not fl:
        return
    t0, t1 = fl["range"]
    w = window(t, t0, t1, 0.3, 0.35)
    if not w:
        return
    a, u = w
    area0, area1 = fl.get("area", (440, 1900))
    y = fl.get("y", 250)
    if fl.get("title"):
        cv.sprite(S.flow_title, (area0 + area1) / 2, y - 138 + 20 * (1 - ease_out(u)), a)
    items = fl["items"]
    cw, gap = CHIP_W, 50
    x = area0 + (area1 - area0 - (len(items) * cw + (len(items) - 1) * gap)) / 2
    for i, (ts, emo, title, sub, st) in enumerate(items):
        if t < ts:
            break
        k = clamp01((t - ts) / 0.35)
        cx = x + i * (cw + gap) + cw / 2
        cv.sprite(chip_sprite(emo, title, sub, st), cx, y + 30 * (1 - ease_out(k)), a * k, 0.7 + 0.3 * ease_back(k))
        if i:
            draw_arrow(cv, (cx - cw / 2 - gap + 8, y), (cx - cw / 2 - 6, y), gfx.ACCENT, ease_out(k), a, bend=0, thick=5)
        if st == "run":
            pulse = 0.5 + 0.5 * math.sin(t * 8)
            draw_rrect(cv, (cx - cw / 2, y - 64, cx + cw / 2, y + 64), gfx.ACCENT, 3, 20, a * k * (0.4 + 0.6 * pulse), glow=10)


HUD_X, HUD_Y = 18, 66
MINI_X, MINI_Y, MINI_ROW = 14, 80, 54


def layer_hud(cv, t, view):
    hud = TL.hud
    if not hud:
        return
    w = window(t, *hud["range"], 0.5, 0.4)
    if not w:
        return
    a0, u = w
    panel, rows, active_spr, steps, mpanel, micons = S.hud
    n = len(hud["items"])
    act = hud.get("active", [(0, 0)])
    idx = prev_idx = act[0][1]
    t_sw = 0
    for ts, v in act:
        if t >= ts:
            prev_idx, idx, t_sw = idx, v, ts
    # 줌인 시 이모지만 남긴 미니 HUD 로 접힘
    m = ease_io(clamp01((view.z - 1.04) / 0.08))
    if m > 0.003:
        am, dx = a0 * m, -30 * (1 - m)
        x, y = MINI_X + dx, MINI_Y
        cv.sprite(mpanel, x, y, am, anchor=(0, 0))
        if idx >= 0:
            ry = y + 16 + idx * MINI_ROW - 4
            draw_rrect(cv, (x + 8, ry, x + 64, ry + MINI_ROW - 2), gfx.ACCENT, 3, 12, am, fill=(*gfx.ACCENT, 70), glow=6)
        cv.sprite(micons, x, y, am, anchor=(0, 0))
        for i in range(n):
            pulse = 0.5 + 0.5 * math.sin(t * 5 + i * 1.3)
            draw_dot(cv, (x + 60, y + 16 + i * MINI_ROW + 6), 5, gfx.GREEN, am * (0.55 + 0.45 * pulse), glow=3)
    a = a0 * (1 - m)
    if a <= 0.003:
        return
    ox = HUD_X - 60 * (1 - ease_out(u)) - 40 * m
    cv.sprite(panel, ox, HUD_Y, a, anchor=(0, 0))
    if idx >= 0:
        k = ease_out(clamp01((t - t_sw) / 0.35))
        y_from = 94 + (prev_idx if prev_idx >= 0 else idx) * 46
        y = y_from + (94 + idx * 46 - y_from) * k
        draw_rrect(cv, (ox + 10, HUD_Y + y, ox + 390, HUD_Y + y + 42), gfx.ACCENT, 2, 10, a, fill=(*gfx.ACCENT, 50))
        draw_rrect(cv, (ox + 10, HUD_Y + y + 6, ox + 15, HUD_Y + y + 36), gfx.ACCENT, 2, 2, a, fill=(*gfx.ACCENT, 255))
    cv.sprite(rows, ox, HUD_Y, a, anchor=(0, 0))
    if idx >= 0:
        cv.sprite(active_spr[idx], ox, HUD_Y, a, anchor=(0, 0))
    for i in range(n):
        pulse = 0.5 + 0.5 * math.sin(t * 5 + i * 1.3)
        draw_dot(cv, (ox + 370, HUD_Y + 94 + i * 46 + 21), 6, gfx.GREEN, a * (0.55 + 0.45 * pulse), glow=4)
    st = [(ts, lb) for ts, lb in hud.get("steps", []) if t >= ts]
    if st:
        t_step, label = st[-1]
        k = ease_out(clamp01((t - t_step) / 0.4))
        cv.sprite(steps[label], ox + 16 * (1 - k), HUD_Y + 46, a * k, anchor=(0, 0))


def layer_subtitle(cv, t):
    cap = TL.caption
    for t0, t1, text in TL.subtitles:
        w = window(t, t0, t1, 0.28, 0.22)
        if not w:
            continue
        a, u = w
        sp = subtitle_sprite(text, size=cap.get("size", 40))
        cv.sprite(sp, W / 2, H - cap.get("bottom", 52) + 22 * (1 - ease_out(u)), a, 0.96 + 0.04 * ease_out(u), anchor=(0.5, 1))


def layer_progress(cv, t):
    if not TL.progress:
        return
    rng = TL.hud["range"] if TL.hud else (TL.title["range"][1] if TL.title else 0, TL.outro["start"] if TL.outro else TL.duration)
    w = window(t, *rng, 0.5, 0.4)
    if not w:
        return
    a = w[0]
    p = clamp01((t - rng[0]) / (rng[1] - rng[0]))
    draw_rrect(cv, (0, H - 7, W, H), (255, 255, 255), 1, 0, a * 0.25, fill=(255, 255, 255, 40))
    if p > 0.002:
        draw_rrect(cv, (0, H - 7, W * p, H), gfx.ACCENT, 1, 0, a, fill=(*gfx.ACCENT, 255), glow=4)


def blur_bg(frame, k):
    if k <= 0.01:
        return frame
    small = cv2.resize(frame, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 6)
    b = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    return cv2.addWeighted(frame, 1 - k, b, k, 0)


def layer_title(cv, t, frame):
    tt = TL.title
    if not tt:
        return frame
    t0, t1 = tt["range"]
    if t > t1:
        return frame
    big, sub, tokens, chip = S.title
    out = clamp01((t - (t1 - 0.55)) / 0.55)
    k = 1 - ease_io(out)
    frame = blur_bg(frame, 0.85 * k)
    frame = (frame.astype(np.float32) * (1 - 0.55 * k)).astype(np.uint8)
    lift = -40 * ease_io(out)
    y0 = 330 if tokens else 400

    def el(sp, y, ts, pop=False):
        u = clamp01((t - ts) / 0.45)
        if u > 0 and sp is not None:
            sc = 0.7 + 0.3 * ease_back(u) if pop else 1.0
            cv.sprite(sp, W / 2, y + 30 * (1 - ease_out(u)) + lift, ease_out(u) * k, sc)

    el(chip, y0, 0.1, True)
    el(big, y0 + 115, 0.3)
    el(sub, y0 + 235, 0.55)
    n = len(tokens)
    for i, sp in enumerate(tokens):
        u = clamp01((t - (0.85 + i * 0.12)) / 0.4)
        if u > 0:
            cx = W / 2 + (i - (n - 1) / 2) * 210
            cv.sprite(sp, cx, y0 + 390 + lift, ease_out(u) * k, 0.4 + 0.6 * ease_back(u))
    return frame


def layer_outro(cv, t, frame):
    oo = TL.outro
    if not oo or t < oo["start"]:
        return frame
    t0 = oo["start"]
    big, stats, chip, foot = S.outro
    k = ease_io(clamp01((t - t0) / 0.6))
    frame = blur_bg(frame, 0.8 * k)
    frame = (frame.astype(np.float32) * (1 - 0.6 * k)).astype(np.uint8)

    def el(sp, x, y, ts, pop=False):
        u = clamp01((t - ts) / 0.45)
        if u > 0 and sp is not None:
            cv.sprite(sp, x, y + 30 * (1 - ease_out(u)), ease_out(u), 0.7 + 0.3 * ease_back(u) if pop else 1.0)

    top = oo.get("top", 300)  # 칩 y 좌표 — PHOTOS 와 함께 쓸 땐 위로 올린다 (예: 110)
    el(chip, W / 2, top, t0 + 0.3, True)
    el(big, W / 2, top + 110, t0 + 0.5)
    n = len(stats)
    for i, sp in enumerate(stats):
        el(sp, W / 2 + (i - (n - 1) / 2) * 470, top + 300, t0 + 0.9 + i * 0.18, True)
    el(foot, W / 2, oo.get("footer_y", top + 470 if n else top + 260), t0 + 1.6)
    return frame


# ================================================================ frame
CANVAS = None


class Ctx:
    """CUSTOM_LAYERS / CUSTOM_FRAME_FX 함수가 받는 컨텍스트."""

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.gfx, self.fx, self.render, self.W, self.H = gfx, fx, __import__(__name__), W, H

    def screen(self, target):
        """'@트랙' 또는 (x, y) 원본 좌표 → 현재 화면 좌표."""
        return self.view.s(self.tl.target(target).pt(self.ts))

    def window(self, t0, t1, fin=0.3, fout=0.25):
        """원본 시각 구간 → (alpha, 진행도) 또는 None."""
        a, b = self.tl.span(t0, t1)
        return window(self.t, a, b, fin, fout)


def _custom(fns, ctx, img):
    for fn in fns:
        ctx.frame = img
        out = fn(ctx)
        if out is not None:
            img = out
    return img


def render_frame(frame, t):
    """frame: 원본 프레임(BGR), t: 출력 시각 → 캔버스(W x H) BGR."""
    global CANVAS
    if CANVAS is None:
        CANVAS = Canvas()
    ts = TL.remap.src(t)
    view = View(t, ts)
    frame = promo.cleanup(frame, ts)
    img = view.warp(letterbox(frame))
    img = fx.frame_fx(img, t)
    img = promo.glows(img, view, t, ts)
    cv = CANVAS
    cv.clear()
    ctx = Ctx(t=t, ts=ts, raw=frame, view=view, cv=cv, tl=TL, frame=img)
    img = _custom(TL.custom_frame_fx, ctx, img)
    img = layer_title(cv, t, img)
    img = layer_highlights(cv, view, t, img, ts)
    layer_links(cv, view, t)
    img = layer_clicks(cv, view, t, img)
    fx.layer_magnify(cv, view, t, ts, frame)
    fx.layer_stickers(cv, view, t, ts)
    fx.layer_callouts(cv, view, t, ts)
    layer_cards(cv, t)
    layer_flow(cv, t)
    layer_hud(cv, t, view)
    fx.layer_photos(cv, t)
    fx.layer_particles(cv, view, t, ts)
    fx.layer_pops(cv, view, t, ts)
    fx.layer_badges(cv, t)
    img = _custom(TL.custom_layers, ctx, img)
    promo.layer_type(cv, t)
    layer_subtitle(cv, t)
    layer_progress(cv, t)
    img = layer_outro(cv, t, img)
    out = cv.composite(img)
    out = promo.bars(out, t)  # 파티클이 레터박스 위로 넘어가지 않게 합성 뒤에 덮는다 (TYPE 은 안전 영역 안에 둔다)
    out = promo.ink(out, t)
    out = promo.overlay_top(out, t)
    fo = TL.fade_out
    fade = clamp01((t - (TL.duration - fo)) / fo) if fo else 0
    if fade > 0:
        out = (out.astype(np.float32) * (1 - fade)).astype(np.uint8)
    return out
