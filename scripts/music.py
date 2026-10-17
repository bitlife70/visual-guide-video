"""경쾌한 배경음(기본 126 BPM 일렉트로 팝) + 타임라인 싱크 효과음을 numpy로 합성한다.

섹션은 영상 길이에 맞춰 자동 배치된다.
  intro  : 패드 + 필터 플럭 + 햇 (기본: 첫 클릭 시점까지, 2~4마디)
  A      : 킥·클랩·햇·오프비트 베이스·플럭 코드
  B      : A + 벨 아르페지오 (후반부 리드 프리뷰)
  build  : 스네어 롤 + 노이즈 라이저 (drop 직전 2마디)
  drop   : 풀 편성 + 리드 훅 + 오픈햇  (MUSIC['drop'] 초, 기본 영상의 70% 지점)
  outro  : 2마디 후 마지막 코드 링아웃
"""
import math

import numpy as np
from scipy import signal

SR = 44100
RNG = np.random.default_rng(7)

PROG = [  # C - G - Am - F  (코드 보이싱, 베이스 루트)
    ([60, 64, 67, 74], 36),
    ([59, 62, 67, 74], 43),
    ([60, 64, 69, 72], 45),
    ([60, 65, 69, 72], 41),
]
HOOK = [  # 마디별 (16분 스텝, 길이, 음)
    [(0, 2, 76), (2, 2, 79), (4, 3, 84), (7, 1, 83), (8, 2, 79), (10, 2, 76), (12, 4, 79)],
    [(0, 2, 74), (2, 2, 79), (4, 3, 83), (7, 1, 81), (8, 2, 79), (10, 2, 74), (12, 4, 71)],
    [(0, 2, 72), (2, 2, 76), (4, 3, 81), (7, 1, 79), (8, 2, 76), (10, 2, 72), (12, 4, 76)],
    [(0, 2, 77), (2, 2, 81), (4, 3, 84), (7, 1, 81), (8, 4, 79), (12, 2, 76), (14, 2, 74)],
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tvec(dur):
    return np.arange(int(dur * SR)) / SR


def add(buf, x, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i < 0:
        x, i = x[-i:], 0
    if i >= buf.shape[1] or len(x) == 0:
        return
    x = x[: buf.shape[1] - i]
    l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    buf[0, i:i + len(x)] += x * gain * l * 1.414
    buf[1, i:i + len(x)] += x * gain * r * 1.414


def lp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, min(fc, SR * 0.45), "low", fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(signal.butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def saw(f, t, phase=0.0):
    return 2 * ((f * t + phase) % 1.0) - 1


# ---------------------------------------------------------------- instruments
def kick():
    t = tvec(0.38)
    f = 48 + 120 * np.exp(-t * 32)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5)
    x[:200] += RNG.standard_normal(200) * np.linspace(0.4, 0, 200)
    return np.tanh(x * 1.6)


def clap():
    t = tvec(0.28)
    n = bp(RNG.standard_normal(len(t)), 900, 3200)
    env = np.exp(-t * 18)
    for d in (0.0, 0.011, 0.022):
        env += 0.6 * np.exp(-np.maximum(t - d, 0) * 160) * (t >= d)
    return n * env * 0.5


def hat(open_=False):
    t = tvec(0.28 if open_ else 0.06)
    n = hp(RNG.standard_normal(len(t)), 7500)
    return n * np.exp(-t * (11 if open_ else 70)) * 0.35


def snare():
    t = tvec(0.2)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    n = bp(RNG.standard_normal(len(t)), 1500, 7000) * np.exp(-t * 22)
    return tone * 0.5 + n * 0.6


def pluck(notes, dur=0.42, cutoff=2600):
    t = tvec(dur)
    x = np.zeros(len(t))
    for m in notes:
        f = hz(m)
        for det, ph in ((-0.12, 0.1), (0.0, 0.5), (0.12, 0.8)):
            x += saw(f * 2 ** (det / 12), t, ph)
    x = lp(x / (len(notes) * 3), cutoff)
    return x * np.exp(-t * 7) * np.minimum(1, t / 0.004)


def pad(notes, dur, cutoff=1400):
    t = tvec(dur)
    x = np.zeros(len(t))
    for m in notes:
        f = hz(m)
        for det in (-0.08, 0.0, 0.08):
            x += saw(f * 2 ** (det / 12), t, RNG.random())
    x = lp(x / (len(notes) * 3), cutoff)
    env = np.minimum(1, t / 0.35) * np.minimum(1, (dur - t) / 0.3)
    return x * env


def bass(m, dur=0.22):
    t = tvec(dur)
    f = hz(m)
    x = 0.6 * saw(f, t) + 0.6 * saw(f * 1.004, t, 0.3) + 0.45 * np.sin(2 * np.pi * f / 2 * t)
    x = lp(x, 700)
    return np.tanh(x * 1.5) * np.exp(-t * 6) * np.minimum(1, t / 0.003)


def bell(m, dur=0.3):
    t = tvec(dur)
    f = hz(m)
    mod = 2.2 * np.exp(-t * 9) * np.sin(2 * np.pi * f * 3.5 * t)
    return np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 11)


def lead(m, dur):
    t = tvec(dur + 0.08)
    f = hz(m) * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.15))
    ph = np.cumsum(f) / SR
    x = 0.55 * (2 * (ph % 1) - 1) + 0.45 * np.sign(np.sin(2 * np.pi * ph))
    x = lp(x, 3800)
    env = np.minimum(1, t / 0.01) * np.where(t < dur, 0.85 + 0.15 * np.exp(-t * 8), np.exp(-(t - dur) * 40))
    return x * env


# ---------------------------------------------------------------- 국악기 (zen 스타일·효과음 공용)
from functools import lru_cache


@lru_cache(512)
def gayageum(m, dur=1.6, bright=0.5, bend=0.0, vib=0.0, seed=0):
    """가야금: Karplus-Strong 현 + 농현(vib, 반음 단위 깊이) + 추성(bend: 시작 음높이 반음 차이 → 0)."""
    f = hz(m)
    L = max(8, int(round(SR / f - 0.5)))
    n = int(SR * (dur + 0.05)) + L + 2
    r = np.random.default_rng(seed * 131 + m)
    y = np.zeros(n + 1)  # y[0] = 0 은 첫 블록의 y[n-L-1] 자리
    y[1:L + 1] = lp(r.uniform(-1, 1, L), 1200 + 5000 * bright)
    decay = 0.9965
    for s in range(L + 1, n + 1, L):
        e = min(s + L, n + 1)
        y[s:e] = decay * 0.5 * (y[s - L:e - L] + y[s - L - 1:e - L - 1])
    y = y[1:]
    t = tvec(dur)
    semi = bend * np.exp(-t / 0.07) + vib * np.minimum(1, np.maximum(0, t - 0.22) / 0.3) * np.sin(2 * np.pi * 4.6 * t)
    ratio = f / (SR / (L + 0.5)) * 2 ** (semi / 12)
    idx = np.cumsum(ratio)
    x = np.interp(idx, np.arange(n), y)
    x = lp(x, 4200) + 0.25 * bp(x, 180, 900)
    return x * np.minimum(1, (dur - t) / 0.08) * 0.9


def daegeum(m, dur, vib=0.35, scoop=0.6):
    """대금: 아래에서 밀어 올리는 시김새 + 점점 깊어지는 떨림 + 숨소리 + 청공의 떨리는 배음."""
    t = tvec(dur + 0.1)
    v = np.minimum(1, np.maximum(0, t - 0.25) / 0.5) * np.sin(2 * np.pi * 5.2 * t)
    semi = -scoop * np.exp(-t / 0.06) + vib * 0.5 * v
    f = hz(m) * 2 ** (semi / 12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.32 * np.sin(2 * ph) + 0.14 * np.sin(3 * ph) + 0.05 * np.sin(4 * ph)
    buzz = hp(np.tanh(3 * np.sin(ph)), 1800) * 0.07
    nz = RNG.standard_normal(len(t))
    breath = bp(nz, hz(m) * 1.2, hz(m) * 4) * (0.12 + 0.35 * np.exp(-t / 0.08)) + hp(nz, 4000) * 0.03
    env = np.minimum(1, t / 0.07) * np.clip((dur + 0.1 - t) / 0.2, 0, 1)
    return (tone * 0.75 + buzz + breath) * env * (1 + 0.12 * v * vib)


def janggu(kind):
    """장구: kung(궁편, 낮은 울림) / deok(채편, 높은 딱) / ghost(약한 채편)."""
    if kind == "kung":
        t = tvec(0.7)
        f = 62 + 70 * np.exp(-t * 25)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
        return np.tanh((body + lp(RNG.standard_normal(len(t)), 700) * np.exp(-t * 40) * 0.4) * 1.5)
    t = tvec(0.25)
    body = np.sin(2 * np.pi * 340 * t) * np.exp(-t * 30) * 0.5 + np.sin(2 * np.pi * 530 * t) * np.exp(-t * 42) * 0.3
    crack = bp(RNG.standard_normal(len(t)), 1800, 6500) * np.exp(-t * 65)
    return (body + crack) * (0.4 if kind == "ghost" else 1.0)


def noise_riser(dur, f0=300, f1=9000):
    n = int(dur * SR)
    x = RNG.standard_normal(n)
    out = np.zeros(n)
    blk = 1024
    zi = None
    for i in range(0, n, blk):
        u = i / max(1, n)
        fc = f0 * (f1 / f0) ** u
        sos = signal.butter(2, [fc * 0.6, min(fc * 1.6, SR * 0.45)], "band", fs=SR, output="sos")
        if zi is None:
            zi = signal.sosfilt_zi(sos) * 0
        out[i:i + blk], zi = signal.sosfilt(sos, x[i:i + blk], zi=zi)
    return out * np.linspace(0, 1, n) ** 2


def crash():
    t = tvec(1.8)
    n = hp(RNG.standard_normal(len(t)), 3500) * np.exp(-t * 2.6) * 0.4
    boom = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 5) * 0.6
    return n + boom


# ---------------------------------------------------------------- SFX
def sfx_click():
    t = tvec(0.09)
    f = 1500 * np.exp(-t * 18) + 600
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
    x[:120] += RNG.standard_normal(120) * np.linspace(0.6, 0, 120)
    return x


def sfx_whoosh(dur=0.5, up=True):
    n = int(dur * SR)
    x = noise_riser(dur, 500 if up else 4000, 4000 if up else 500)
    w = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    return x / (np.abs(x).max() + 1e-9) * w


def sfx_bling():
    t = tvec(0.45)
    return (np.sin(2 * np.pi * 1318.5 * t) + 0.6 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t * 9) * np.minimum(1, t / 0.003)


# ---------------------------------------------------------------- reverb (블록 단위 comb/allpass)
def _comb(x, d, g):
    y = x.copy()
    for i in range(d, len(y), d):
        e = min(i + d, len(y))
        y[i:e] += g * y[i - d:e - d]
    return y


def _allpass(x, d, g):
    y = np.zeros_like(x)
    y[:d] = -g * x[:d]
    for i in range(d, len(x), d):
        e = min(i + d, len(x))
        y[i:e] = -g * x[i:e] + x[i - d:e - d] + g * y[i - d:e - d]
    return y


def reverb(x, seed=0):
    ds = [1557, 1617, 1491, 1422] if seed == 0 else [1601, 1559, 1453, 1381]
    y = sum(_comb(x, d, 0.78) for d in ds) / 4
    for d in (225, 556):
        y = _allpass(y, d + seed * 13, 0.5)
    return lp(y, 5000)


# ---------------------------------------------------------------- arrangement
def sections(tl, bar, dur=None):
    dur = dur or tl.duration
    end_bar = max(4, int((dur - 0.3) // bar))  # 마지막 코드 링아웃 마디
    mu = tl.music
    if mu.get("intro_bars"):
        intro = int(mu["intro_bars"])
    elif tl.clicks:
        intro = int(min(4, max(2, round(tl.clicks[0][0] / bar))))
    else:
        intro = 4
    intro = min(intro, max(1, end_bar // 4))
    drop = round(mu["drop"] / bar) if mu.get("drop") else round(end_bar * 0.7)
    drop = int(min(max(drop, intro + 2), max(intro + 2, end_bar - 2)))
    build = max(intro, drop - 2)
    outro = max(drop, end_bar - 2)
    mid = intro + (build - intro) // 2
    return dict(intro=intro, mid=mid, build=build, drop=drop, outro=outro, end=end_bar)


def music_pop(tl, dur):
    bpm = tl.music.get("bpm") or 126
    tr = int(tl.music.get("transpose", 0))
    beat = 60 / bpm
    bar = 4 * beat
    step = beat / 4
    N = int(SR * (dur + 0.5))
    sec = sections(tl, bar, dur)
    drums, inst, send = np.zeros((2, N)), np.zeros((2, N)), np.zeros((2, N))
    K, C, Hc, Ho, Sn = kick(), clap(), hat(), hat(True), snare()
    kicks = []
    lead_from = sec["mid"] + (sec["build"] - sec["mid"]) // 2
    for b in range(sec["end"] + 1):
        chord, root = PROG[b % 4]
        chord = [n + tr for n in chord]
        root += tr
        intro = b < sec["intro"]
        A = sec["intro"] <= b < sec["mid"]
        B = sec["mid"] <= b < sec["build"]
        build = sec["build"] <= b < sec["drop"]
        drop = sec["drop"] <= b < sec["outro"]
        outro = sec["outro"] <= b < sec["end"]
        final = b == sec["end"]
        groove = A or B or drop or outro
        t0 = b * bar
        # --- drums
        if groove or (build and b == sec["build"]):
            for q in range(4):
                if build and q % 2:
                    continue
                add(drums, K, t0 + q * beat, 0.78)
                kicks.append(t0 + q * beat)
        if groove:
            for q in (1, 3):
                add(drums, C, t0 + q * beat, 0.55, 0.05)
                add(send, C, t0 + q * beat, 0.18)
        if b >= min(2, sec["intro"]) and not final:
            for e in range(8):
                if e % 2 == 1:
                    add(drums, Ho if drop else Hc, t0 + e * beat / 2, 0.33 if drop else 0.45, 0.25)
                elif not intro:
                    add(drums, Hc, t0 + e * beat / 2 + step, 0.16, -0.25)
        if b == sec["intro"] - 1:
            for s in range(8, 16):
                add(drums, Sn, t0 + s * step, 0.12 + 0.3 * (s - 8) / 8, 0.1)
        if build:
            k = b - sec["build"]
            nb = max(1, sec["drop"] - sec["build"])
            for s in range(0, 16, 2 if k < nb - 1 else 1):
                add(drums, Sn, t0 + s * step, 0.15 + 0.5 * ((k * 16 + s) / (nb * 16)), 0.1)
        # --- bass (오프비트 8분)
        if groove or (build and b == sec["build"]):
            for e in range(1, 8, 2):
                add(inst, bass(root), t0 + e * beat / 2, 0.55)
            if drop:
                for e in (0, 4):
                    add(inst, bass(root, 0.12), t0 + e * beat / 2 + step * 3, 0.3)
        # --- chords
        if intro:
            cut = 900 + 1800 * (b / max(1, sec["intro"]))
        elif build:
            cut = 1500 + 2500 * (b - sec["build"]) / max(1, sec["drop"] - sec["build"])
        else:
            cut = 2800
        if not final:
            g = 1.9 if intro else 1.0
            for s, ln in ((0, 3), (3, 3), (6, 4), (10, 2), (12, 4)):
                p = pluck(chord, ln * step + 0.12, cutoff=min(cut, 4500))
                add(inst, p, t0 + s * step, 0.42 * g, -0.15)
                add(inst, p, t0 + s * step + 0.012, 0.32 * g, 0.35)
                add(send, p, t0 + s * step, 0.22)
        if intro or outro or build or final:
            pd = pad([n - 12 for n in chord[:3]] + chord, bar + 0.05, 1000 if intro else 1600)
            add(inst, pd, t0, 0.55 if intro else (0.4 if final else 0.28))
            add(send, pd, t0, 0.25)
        # --- arp
        if B or drop:
            tones = sorted(chord) + [n + 12 for n in sorted(chord)]
            for s in range(16):
                m = tones[(s * 3) % len(tones)] + 12
                add(inst, bell(m), t0 + s * step, 0.12 if B else 0.08, 0.4 * math.sin(s))
                add(send, bell(m), t0 + s * step, 0.08)
        # --- lead hook
        if (B and b >= lead_from) or drop:
            for s, ln, m in HOOK[b % 4]:
                x = lead(m + tr if drop else m + tr - 12, ln * step)
                add(inst, x, t0 + s * step, 0.3 if drop else 0.16)
                add(send, x, t0 + s * step, 0.2)
                add(send, x, t0 + s * step + beat * 0.75, 0.16)  # 점8분 딜레이
        if final:
            add(inst, pluck(chord, 2.5, 3000), t0, 0.6)
            add(send, crash(), t0, 0.3)
    if sec["drop"] > sec["build"]:
        add(drums, noise_riser(bar * (sec["drop"] - sec["build"])), sec["build"] * bar, 0.35)
    if sec["intro"] >= 1:
        add(drums, noise_riser(bar * 0.5, 800, 8000), (sec["intro"] - 0.5) * bar, 0.18)
    for b in sorted({sec["intro"], sec["mid"], sec["drop"], sec["end"]}):
        add(drums, crash(), b * bar, 0.35 if b == sec["intro"] else 0.5)
        add(send, crash(), b * bar, 0.15)
    # 사이드체인 펌핑
    t = np.arange(N) / SR
    duck = np.ones(N)
    for tk in kicks:
        i0 = int(tk * SR)
        i1 = min(N, i0 + int(0.4 * SR))
        if i0 >= N:
            continue
        duck[i0:i1] = np.minimum(duck[i0:i1], 1 - 0.6 * np.exp(-(t[i0:i1] - tk) / 0.11))
    inst *= duck
    rev = np.stack([reverb(send[0], 0), reverb(send[1], 1)])
    return master(drums + inst + rev * 0.9, dur), sec, bar


def master(x, dur):
    x = np.stack([hp(c, 30) for c in x])
    x = x / (np.abs(x).max() + 1e-9)
    x = np.tanh(x * 1.6) / np.tanh(1.6)
    t = np.arange(x.shape[1]) / SR
    fade = np.clip((dur - t) / 1.6, 0, 1) ** 1.5 * np.clip(t / 0.05, 0, 1)
    return x * fade * 0.89


def build_music(tl):
    """MUSIC['style'] 별 BGM. MUSIC['end'] 가 있으면 그 시각에 음악이 끝난다(end_fx: 'fade' | 'scratch' | 'cut')."""
    style = tl.music.get("style", "pop")
    end = tl.music.get("end")
    start = tl.music.get("start") or 0.0  # MUSIC['start']: 이 시각에 음악이 시작 (예: 생일 노래가 끝난 뒤)
    dur = (min(tl.duration, end) if end else tl.duration) - start
    src = tl
    if start:
        import types
        src = types.SimpleNamespace(**vars(tl))
        src.music = dict(tl.music)
        src.clicks = []
        if src.music.get("drop"):
            src.music["drop"] = src.music["drop"] - start
        if not src.music.get("intro_bars"):
            src.music["intro_bars"] = 1
    if style == "pop":
        x, sec, bar = music_pop(src, dur)
    else:
        import styles
        x, sec, bar = styles.STYLES[style](src, dur)
    N = int(SR * (tl.duration + 0.5))
    out = np.zeros((2, N))
    i0 = int(start * SR)
    n = min(N - i0, x.shape[1])
    out[:, i0:i0 + n] = x[:, :n]
    if end and end < tl.duration:
        i = int(end * SR)
        kind = tl.music.get("end_fx", "fade")
        fl = int(SR * (0.03 if kind in ("scratch", "cut") else 0.8))
        i0 = max(0, i - fl)
        out[:, i0:i] *= np.linspace(1, 0, i - i0)[None, :]
        out[:, i:] = 0
    return out, sec, bar


# ---------------------------------------------------------------- SFX 라이브러리 (SFX = [(t, "이름", gain, pan)])
def sfx_hit():
    t = tvec(0.35)
    f = 60 + 140 * np.exp(-t * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)
    n = lp(RNG.standard_normal(len(t)), 3000) * np.exp(-t * 40)
    return np.tanh((body + 0.7 * n) * 1.8)


def sfx_boom():
    t = tvec(1.6)
    f = 30 + 70 * np.exp(-t * 5)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    n = lp(RNG.standard_normal(len(t)), 1800) * np.exp(-t * 6)
    return np.tanh((sub + 0.5 * n) * 1.5)


def sfx_clang():
    t = tvec(0.9)
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in
            ((523, 0.5, 5), (1187, 0.45, 6), (1873, 0.35, 8), (2711, 0.3, 10), (3907, 0.2, 14)))
    x += hp(RNG.standard_normal(len(t)), 4000) * np.exp(-t * 50) * 0.6
    return x


def sfx_pop():
    t = tvec(0.12)
    f = 380 + 700 * (t / 0.12)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26) * np.minimum(1, t / 0.002)


def sfx_ding():
    t = tvec(1.1)
    return (np.sin(2 * np.pi * 1760 * t) + 0.4 * np.sin(2 * np.pi * 2640 * t) + 0.2 * np.sin(2 * np.pi * 4400 * t)) * np.exp(-t * 4)


def sfx_scratch():
    t = tvec(0.55)
    rate = np.sin(2 * np.pi * 3.2 * t) ** 2 * 4 + 0.3
    ph = np.cumsum(rate) / SR
    src = RNG.standard_normal(int(SR * 3))
    x = np.interp(ph * SR * 0.9, np.arange(len(src)), src)
    x = bp(x, 400, 3500) * (0.4 + 0.6 * rate / 4.3)
    return x * np.minimum(1, (0.55 - t) / 0.05)


def sfx_sad_trombone():
    out = []
    for i, (m, d) in enumerate(((58, 0.42), (57, 0.42), (56, 0.42), (55, 1.4))):
        t = tvec(d)
        vib = 1 + (0.012 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.3) if i == 3 else 0)
        bend = 1 - (0.03 * (t / d) if i == 3 else 0)
        f = hz(m) * vib * bend
        ph = np.cumsum(f) / SR
        x = 0.6 * (2 * (ph % 1) - 1) + 0.4 * np.sin(2 * np.pi * ph)
        wah = 600 + 1400 * np.minimum(1, t / 0.12) * (1 - 0.5 * t / d)
        y = np.zeros_like(x)
        for k in range(0, len(x), 512):  # 블록 단위 와와 필터
            y[k:k + 512] = lp(x[k:k + 512], wah[k])
        env = np.minimum(1, t / 0.03) * np.minimum(1, (d - t) / 0.06)
        out.append(y * env)
    return np.concatenate(out) * 0.9


def sfx_heartbeat():
    t = tvec(0.9)
    def thump(t0, g):
        u = np.maximum(t - t0, 0)
        return np.sin(2 * np.pi * (45 + 30 * np.exp(-u * 30)) * u) * np.exp(-u * 18) * (t >= t0) * g
    return np.tanh((thump(0, 1.0) + thump(0.24, 0.75)) * 2)


def sfx_shutter():
    t = tvec(0.25)
    x = hp(RNG.standard_normal(len(t)), 2000)
    env = np.exp(-t * 90) + 0.7 * np.exp(-np.maximum(t - 0.09, 0) * 90) * (t >= 0.09)
    return x * env * 0.8


def sfx_slowmo():
    t = tvec(1.2)
    f = 220 * np.exp(-t * 1.6) + 40
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.5)
    return 0.6 * tone + 0.5 * sfx_whoosh(1.2, False)


def sfx_party_horn():
    t = tvec(0.9)
    f = 420 * (1 + 0.5 * np.minimum(1, t / 0.12)) * (1 + 0.01 * np.sin(2 * np.pi * 18 * t))
    ph = np.cumsum(f) / SR
    x = 0.6 * np.sign(np.sin(2 * np.pi * ph)) + 0.4 * (2 * (ph % 1) - 1)
    x = bp(x, 500, 3500) * np.minimum(1, t / 0.02) * np.minimum(1, (0.9 - t) / 0.15)
    return x * 0.7


def sfx_twinkle():
    out = np.zeros(int(SR * 1.4))
    for k, m in enumerate((84, 88, 91, 96, 100, 103)):
        x = bell(m, 0.6)
        i = int(k * 0.07 * SR)
        out[i:i + len(x)] += x[: len(out) - i] * (0.9 - k * 0.08)
    return out * 0.6


def sfx_confetti():
    t = tvec(1.2)
    n = np.zeros(len(t))
    r = np.random.default_rng(3)
    for k in range(40):  # 종이 조각 바스락 + 펑
        i = int(r.random() * 0.9 * SR)
        L = int(0.02 * SR)
        n[i:i + L] += r.standard_normal(L) * np.exp(-np.arange(L) / (0.004 * SR)) * r.uniform(0.2, 0.6)
    boom = np.sin(2 * np.pi * (90 + 200 * np.exp(-t * 40)) * t) * np.exp(-t * 18)
    return hp(n, 2500) + boom * 0.8


# ---------------------------------------------------------------- 자연·전통 효과음 (광고·여행 영상)
def sfx_stamp():
    """도장 찍는 소리: 묵직한 툭 + 종이 질감."""
    t = tvec(0.6)
    thud = np.sin(2 * np.pi * np.cumsum(55 + 110 * np.exp(-t * 40)) / SR) * np.exp(-t * 13)
    paper = bp(RNG.standard_normal(len(t)), 700, 4500) * np.exp(-t * 50) * 0.55
    return np.tanh((thud + paper) * 1.7)


def sfx_temple_bell(dur=7.0):
    """범종: 비화성 배음 + 맥놀이(두 배음이 살짝 어긋나 울렁임) + 당목 타격."""
    t = tvec(dur)
    f0 = 118.0
    x = np.zeros(len(t))
    for ratio, amp, dec in ((0.5, 0.55, 0.22), (1.0, 1.0, 0.38), (1.19, 0.4, 0.6), (1.5, 0.3, 0.8), (2.0, 0.45, 0.95),
                            (2.52, 0.22, 1.5), (3.03, 0.16, 1.9), (4.18, 0.1, 2.8)):
        for det in (-0.32, 0.32):
            x += amp * np.sin(2 * np.pi * (f0 * ratio + det) * t + ratio) * np.exp(-t * dec)
    strike = lp(RNG.standard_normal(len(t)), 900) * np.exp(-t * 18) * 1.2 + np.sin(2 * np.pi * 55 * t) * np.exp(-t * 9)
    return (x / 4 + strike * 0.5) * np.minimum(1, t / 0.004)


def sfx_ink(dur=1.4):
    """먹물 번짐: 부풀었다 가라앉는 저역 스웰."""
    t = tvec(dur)
    env = np.sin(np.pi * t / dur) ** 2
    n = RNG.standard_normal(len(t))
    out = np.zeros(len(t))
    fc = 250 + 1300 * env
    for k in range(0, len(t), 1024):
        out[k:k + 1024] = lp(n[k:k + 1024], fc[k])
    return out * env * 0.6 + np.sin(2 * np.pi * 42 * t) * env * 0.5


def sfx_gliss(up=True):
    """가야금 글리산도(5음계 훑기)."""
    notes = [62, 65, 67, 69, 72, 74, 77, 79, 81, 84, 86, 89]
    notes = notes if up else notes[::-1]
    out = np.zeros(int(SR * 2.6))
    for k, m in enumerate(notes):
        x = gayageum(m, 1.6, 0.6, 0.0, 0.0, k)
        i = int(k * 0.045 * SR)
        out[i:i + len(x)] += x[: len(out) - i] * (0.55 + 0.04 * k)
    return out * 0.7


def sfx_birds(dur=4.0):
    """새소리: 짧은 휘파람 지저귐이 드문드문."""
    out = np.zeros(int(SR * dur))
    r = np.random.default_rng(int(dur * 10))
    for _ in range(int(dur * 1.6)):
        t0 = r.random() * max(0.1, dur - 0.6)
        f0 = r.uniform(2600, 4200)
        for j in range(r.integers(2, 5)):
            t = tvec(r.uniform(0.05, 0.1))
            f = f0 * (1 + 0.35 * np.sin(np.pi * t / t[-1])) * r.uniform(0.95, 1.08)
            x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / t[-1]) ** 2
            i = int((t0 + j * 0.11) * SR)
            out[i:i + len(x)] += x[: max(0, len(out) - i)] * r.uniform(0.3, 0.7)
    return out * 0.5


def _ambience(dur, lo, hi, lfo, depth, seed):
    n = int(SR * dur)
    t = np.arange(n) / SR
    x = bp(np.random.default_rng(seed).standard_normal(n), lo, hi)
    env = 1 - depth + depth * (0.5 + 0.5 * np.sin(2 * np.pi * lfo * t - np.pi / 2))
    fade = np.minimum(1, t / 0.8) * np.minimum(1, (dur - t) / 0.8)
    return x * env * fade


SFX_LIB = {
    "stamp": sfx_stamp, "temple_bell": sfx_temple_bell, "ink": sfx_ink, "gliss": sfx_gliss,
    "gliss_down": lambda: sfx_gliss(False), "birds": sfx_birds,
    "waves": lambda dur=8.0: _ambience(dur, 120, 1600, 0.16, 0.7, 5),
    "wind": lambda dur=8.0: _ambience(dur, 250, 1100, 0.11, 0.6, 6) * 1.3,
    "water": lambda dur=8.0: _ambience(dur, 300, 7000, 0.4, 0.15, 7) * 0.8,
    "click": sfx_click, "bling": sfx_bling, "hit": sfx_hit, "boom": sfx_boom, "clang": sfx_clang, "pop": sfx_pop,
    "ding": sfx_ding, "scratch": sfx_scratch, "sad_trombone": sfx_sad_trombone, "heartbeat": sfx_heartbeat,
    "shutter": sfx_shutter, "slowmo": sfx_slowmo, "crash": crash,
    "whoosh": lambda: sfx_whoosh(0.5, True), "whoosh_down": lambda: sfx_whoosh(0.6, False),
    "riser": lambda: noise_riser(1.5, 400, 9000) / 3,
    "party_horn": sfx_party_horn, "twinkle": sfx_twinkle, "confetti": sfx_confetti,
}
IMPACT_SFX = {"hit": (("hit", 0.9),), "heavy": (("boom", 0.8), ("hit", 0.6)), "crit": (("boom", 1.0), ("hit", 0.8)),
              "damage": (("hit", 0.8),), "block": (("clang", 0.6),), "parry": (("clang", 0.7), ("ding", 0.25))}


def make_sfx(name):
    """'이름' 또는 '이름:길이초' (birds·waves·wind·water·temple_bell·ink 처럼 길이를 받는 효과음)."""
    base, _, arg = name.partition(":")
    return SFX_LIB[base](float(arg)) if arg else SFX_LIB[base]()


def build_sfx(tl):
    N = int(SR * (tl.duration + 0.5))
    fx = np.zeros((2, N))
    for t0, name, gain, pan in tl.sfx:
        add(fx, make_sfx(name), t0, 0.6 * gain, pan)
    import promo
    promo.add_sfx(tl, fx, add, make_sfx)
    for ti, kind in tl.impacts:
        for name, g in IMPACT_SFX.get(kind, ()):
            add(fx, SFX_LIB[name](), ti, 0.55 * g)
    for a, b, _, opt in tl.freezes:
        if opt.get("sfx", True):
            add(fx, sfx_shutter(), a, 0.4)
    for a, b, kind, opt in tl.particles:
        if opt.get("sfx", True) and opt.get("burst"):
            add(fx, sfx_confetti() if kind == "confetti" else sfx_twinkle(), a, 0.35)
    for ph in tl.photos:
        add(fx, sfx_whoosh(0.45, False), ph[0], 0.15)
        add(fx, sfx_pop(), ph[0] + 0.4, 0.12)
    for a, b, rate, _ in tl.speed_labels:
        if rate < 1:
            add(fx, sfx_slowmo(), a, 0.3)
    for a, *_ in tl.magnify:
        add(fx, sfx_whoosh(0.45, True), a, 0.18)
        add(fx, sfx_bling(), a + 0.35, 0.08)
    for a, b, where, text, style in tl.pops:
        add(fx, sfx_hit() if style in ("impact", "danger") else sfx_pop(), a, 0.3 if style in ("impact", "danger") else 0.25)
    for a, *_ in tl.callouts:
        add(fx, sfx_pop(), a, 0.12)
    for a, *_ in tl.stickers:
        add(fx, sfx_pop(), a, 0.1)
    if tl.music.get("end") and tl.music.get("end_fx") == "scratch":
        add(fx, sfx_scratch(), tl.music["end"] - 0.05, 0.5)
    for fn in tl.custom_sfx:
        fn(dict(buf=fx, add=add, lib=SFX_LIB, tl=tl, SR=SR))
    for tc, pos, label in tl.clicks:
        pan = (pos[0] / 1920 - 0.5) * 0.8
        add(fx, sfx_click(), tc, 0.5, pan)
        if label:
            add(fx, sfx_bling(), tc - 0.42, 0.10, pan)
    prev = tl.shots[0]
    for shot in tl.shots[1:]:
        dz = math.log(shot["z"]) - math.log(prev["z"])
        if abs(dz) > 0.25 and shot["dur"] < 1.5 and not shot.get("silent"):
            add(fx, sfx_whoosh(max(0.35, shot["dur"]), dz > 0), shot["t"], 0.16 + 0.06 * min(1, abs(dz)))
        prev = shot
    for c in tl.cards:
        add(fx, sfx_bling(), c[0], 0.08, 0.5)
    for h in tl.highlights:
        add(fx, sfx_bling(), h[0], 0.05, -0.2)
    if tl.flow:
        for item in tl.flow["items"]:
            add(fx, sfx_click(), item[0], 0.25)
            add(fx, sfx_bling(), item[0], 0.07)
    if tl.title:
        add(fx, sfx_whoosh(0.6, True), 0.05, 0.25)
    if tl.outro:
        add(fx, sfx_whoosh(0.6, True), tl.outro["start"], 0.2)
    peak = np.abs(fx).max()
    return fx / peak * 0.55 if peak > 0 else fx
