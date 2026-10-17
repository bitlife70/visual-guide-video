"""BGM 스타일 (MUSIC['style']).

  pop   : 126 BPM 일렉트로 팝 (music.py, 화면녹화 기본)
  epic  : 96 BPM 트레일러풍 — 타이코·스타카토 현·브라스 '브람'·합창 패드 (게임 기본, D 단조)
  chill : 82 BPM 로파이 — 일렉피아노·스윙 드럼·바이닐 노이즈 (브이로그 기본)
  cute  : 132 BPM 마림바·피치카토·글로켄 (애니메이션 기본, C 장조)
  zen   : 80 BPM 동양풍 시네마틱 — 가야금·대금·장구·북·합창 (자연·여행·문화 광고, D 단조 5음계). MUSIC['arc'] 로 장면별 에너지

모든 스타일이 music.sections() 의 섹션 구조(intro/A/B/build/drop/outro)를 따르므로 MUSIC['drop'] 이 동일하게 동작한다.
"""
import math

import numpy as np

from music import (RNG, SR, add, bell, bp, crash, daegeum, gayageum, hat, hp, hz, janggu, kick, lead, lp, master,
                   noise_riser, pad, pluck, reverb, saw, sections, snare, tvec, clap)


def _sidechain(x, kicks, N, depth=0.5, rel=0.12):
    t = np.arange(N) / SR
    g = np.ones(N)
    for tk in kicks:
        i0 = int(tk * SR)
        i1 = min(N, i0 + int(0.4 * SR))
        if i0 < N:
            g[i0:i1] = np.minimum(g[i0:i1], 1 - depth * np.exp(-(t[i0:i1] - tk) / rel))
    return x * g


def _finish(drums, inst, send, kicks, N, dur, sc=0.5):
    inst = _sidechain(inst, kicks, N, sc)
    rev = np.stack([reverb(send[0], 0), reverb(send[1], 1)])
    return master(drums + inst + rev * 0.9, dur)


def _flags(b, sec):
    return dict(intro=b < sec["intro"], A=sec["intro"] <= b < sec["mid"], B=sec["mid"] <= b < sec["build"],
                build=sec["build"] <= b < sec["drop"], drop=sec["drop"] <= b < sec["outro"],
                outro=sec["outro"] <= b < sec["end"], final=b == sec["end"])


# ================================================================ EPIC
def taiko(f0=120, f1=52, dec=5.5, dur=0.9):
    t = tvec(dur)
    f = f1 + (f0 - f1) * np.exp(-t * 28)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * dec)
    skin = lp(RNG.standard_normal(len(t)), 900) * np.exp(-t * 35) * 0.8
    return np.tanh((body + skin) * 1.8)


def stac(m, dur=0.16, cut=2200):
    t = tvec(dur + 0.05)
    x = sum(saw(hz(m) * 2 ** (d / 12), t, ph) for d, ph in ((-0.1, 0.2), (0, 0.6), (0.1, 0.9))) / 3
    x = lp(x, cut)
    return x * np.minimum(1, t / 0.006) * np.exp(-t * 9)


def braam(root, dur):
    t = tvec(dur)
    x = np.zeros(len(t))
    for m, g in ((root - 12, 0.9), (root, 0.7), (root + 7, 0.5), (root + 12, 0.35)):
        for d in (-0.15, 0.0, 0.15):
            x += g * saw(hz(m) * 2 ** (d / 12), t, RNG.random())
    out = np.zeros(len(t))
    env_c = 250 + 2600 * np.minimum(1, t / 0.25) * np.exp(-np.maximum(t - 0.25, 0) * 2.2)
    for k in range(0, len(t), 1024):
        out[k:k + 1024] = lp(x[k:k + 1024], env_c[k])
    env = np.minimum(1, t / 0.07) * np.minimum(1, (dur - t) / 0.25)
    return np.tanh(out / 6 * env * 2.2)


def choir(notes, dur):
    t = tvec(dur)
    x = np.zeros(len(t))
    for m in notes:
        for d in (-0.07, 0.0, 0.07):
            x += saw(hz(m) * 2 ** (d / 12), t, RNG.random())
    x = (bp(x, 550, 900) * 1.0 + bp(x, 1000, 1350) * 0.6 + bp(x, 2300, 2800) * 0.15) / len(notes)
    env = np.minimum(1, t / 0.6) * np.minimum(1, (dur - t) / 0.5)
    return x * env * 1.6


def impact_hit():
    t = tvec(2.5)
    f = 28 + 60 * np.exp(-t * 3)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    n = lp(RNG.standard_normal(len(t)), 2500) * np.exp(-t * 3.5) * 0.5
    return np.tanh((sub + n) * 1.6)


EPIC_PROG = [([62, 65, 69], 38), ([58, 62, 65], 34), ([60, 65, 69], 41), ([60, 64, 67], 36)]  # Dm Bb F C
EPIC_HOOK = [
    [(0, 6, 74), (6, 2, 72), (8, 4, 69), (12, 4, 72)],
    [(0, 6, 70), (6, 2, 69), (8, 8, 65)],
    [(0, 6, 72), (6, 2, 74), (8, 4, 77), (12, 4, 76)],
    [(0, 8, 76), (8, 4, 74), (12, 4, 72)],
]
TAIKO_A = [0, 6, 8, 14]
TAIKO_B = [0, 3, 6, 8, 11, 14]


def music_epic(tl, dur):
    bpm = tl.music.get("bpm") or 96
    tr = int(tl.music.get("transpose", 0))
    beat = 60 / bpm
    bar, step = 4 * beat, beat / 4
    N = int(SR * (dur + 3))
    sec = sections(tl, bar, dur)
    drums, inst, send = np.zeros((2, N)), np.zeros((2, N)), np.zeros((2, N))
    TK, TKs, TOM = taiko(), taiko(140, 70, 9, 0.5), taiko(230, 140, 12, 0.35)
    kicks = []
    for b in range(sec["end"] + 1):
        chord, root = EPIC_PROG[b % 4]
        chord = [n + tr for n in chord]
        root += tr
        f = _flags(b, sec)
        t0 = b * bar
        # 타이코
        if f["intro"]:
            add(drums, TK, t0, 0.55)
        elif f["A"] or f["outro"]:
            for s in TAIKO_A:
                add(drums, TK if s in (0, 8) else TKs, t0 + s * step, 0.8 if s in (0, 8) else 0.5, 0.15 * math.sin(s))
            kicks.append(t0)
        elif f["B"] or f["drop"]:
            for s in TAIKO_B:
                add(drums, TK if s in (0, 8) else TKs, t0 + s * step, 0.9 if s in (0, 8) else 0.55, 0.2 * math.sin(s))
            kicks += [t0, t0 + 8 * step]
            if b % 4 == 3:
                for s in (12, 13, 14, 15):
                    add(drums, TOM, t0 + s * step, 0.35 + 0.1 * (s - 12), -0.3 + 0.2 * (s - 12))
            if f["drop"]:
                for e in range(8):
                    add(drums, hat(e % 2 == 1), t0 + e * beat / 2, 0.18, 0.3)
        elif f["build"]:
            k = b - sec["build"]
            nb = max(1, sec["drop"] - sec["build"])
            div = 4 if k < nb - 1 else 2
            for s in range(0, 16, div if k < nb - 1 else 1):
                add(drums, TKs if s % 4 else TK, t0 + s * step, 0.35 + 0.5 * ((k * 16 + s) / (nb * 16)))
            add(drums, snare(), t0 + 15 * step, 0.3)
        # 스타카토 현 오스티나토
        if not f["intro"] and not f["final"]:
            pat = [0, 0, 7, 0, 0, 7, 12, 7] if not (f["B"] or f["drop"] or f["build"]) else [0, 0, 7, 0, 12, 0, 7, 3]
            sub = 2 if (f["A"] or f["outro"]) else 1
            third = 3 if b % 4 == 0 else 4  # Dm 만 단3도
            for s in range(0, 16, sub):
                p = pat[(s // sub) % 8]
                m = root + 12 + (third if p == 3 else p)
                add(inst, stac(m, 0.14, 1800 if f["A"] else 2600), t0 + s * step, 0.32 if sub == 1 else 0.38, -0.25)
                add(inst, stac(m + 12, 0.12, 3000), t0 + s * step + 0.008, 0.14, 0.35)
        # 합창·패드
        if f["intro"] or f["drop"] or f["outro"] or f["final"] or f["B"]:
            ch = choir([n for n in chord] + [chord[0] + 12], bar + 0.4)
            g = 0.5 if f["intro"] else 0.34 if f["B"] else 0.42
            add(inst, ch, t0, g)
            add(send, ch, t0, 0.3)
        if f["intro"] or f["A"]:
            add(inst, pad([root, root + 7], bar + 0.05, 600), t0, 0.5)
        # 브라스 브람 (드롭 매 마디 첫 박)
        if f["drop"]:
            br = braam(root, bar * 0.95)
            add(inst, br, t0, 0.55)
            add(send, br, t0, 0.2)
        # 멜로디 (드롭)
        if f["drop"]:
            for s, ln, m in EPIC_HOOK[b % 4]:
                x = lead(m + tr, ln * step)
                add(inst, lp(x, 2600), t0 + s * step, 0.22)
                add(send, x, t0 + s * step, 0.25)
        if f["final"]:
            add(inst, choir(chord + [chord[0] + 12], 3.0), t0, 0.5)
            add(drums, impact_hit(), t0, 0.8)
            add(send, crash(), t0, 0.25)
    if sec["drop"] > sec["build"]:
        add(drums, noise_riser(bar * (sec["drop"] - sec["build"]), 200, 7000), sec["build"] * bar, 0.35)
    for b in sorted({sec["intro"], sec["drop"]}):
        add(drums, impact_hit(), b * bar, 0.75 if b == sec["drop"] else 0.5)
        add(send, crash(), b * bar, 0.2)
    return _finish(drums, inst, send, kicks, N, dur, 0.35), sec, bar


# ================================================================ CHILL (lo-fi)
def epiano(notes, dur):
    t = tvec(dur)
    x = np.zeros(len(t))
    for m in notes:
        f = hz(m)
        idx = 1.8 * np.exp(-t * 6)
        x += np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t)) * np.exp(-t * 1.6)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)
    return lp(x / len(notes), 3500) * trem * np.minimum(1, t / 0.004) * np.minimum(1, (dur - t) / 0.1)


def vinyl(dur):
    n = int(dur * SR)
    hiss = lp(RNG.standard_normal(n), 5000) * 0.015
    pops = np.zeros(n)
    idx = RNG.integers(0, n, int(dur * 9))
    pops[idx] = RNG.standard_normal(len(idx)) * 0.5
    return hiss + hp(pops, 1500)


CHILL_PROG = [([65, 69, 72, 76], 41), ([64, 67, 71, 74], 40), ([62, 65, 69, 72], 38), ([60, 64, 67, 71], 36)]
CHILL_MEL = [[(0, 3, 81), (4, 2, 79), (6, 6, 76)], [(2, 2, 79), (4, 4, 76), (10, 4, 74)],
             [(0, 3, 77), (4, 2, 76), (6, 6, 72)], [(0, 8, 76), (10, 2, 74), (12, 4, 72)]]


def music_chill(tl, dur):
    bpm = tl.music.get("bpm") or 82
    tr = int(tl.music.get("transpose", 0))
    beat = 60 / bpm
    bar, step = 4 * beat, beat / 4
    sw = step * 0.18  # 스윙
    N = int(SR * (dur + 3))
    sec = sections(tl, bar, dur)
    drums, inst, send = np.zeros((2, N)), np.zeros((2, N)), np.zeros((2, N))
    K = lp(kick(), 900)
    S = lp(snare(), 3500)
    kicks = []
    for b in range(sec["end"] + 1):
        chord, root = CHILL_PROG[b % 4]
        chord = [n + tr for n in chord]
        root += tr
        f = _flags(b, sec)
        t0 = b * bar
        groove = not (f["intro"] or f["final"])
        if groove:
            for s in (0, 7, 10):
                add(drums, K, t0 + s * step + (sw if s % 2 else 0), 0.7)
                kicks.append(t0 + s * step)
            for s in (4, 12):
                add(drums, S, t0 + s * step, 0.42, 0.05)
                add(send, S, t0 + s * step, 0.15)
            for s in range(0, 16, 2):
                add(drums, lp(hat(), 9000), t0 + s * step + (sw if s % 4 == 2 else 0), 0.22 if s % 4 else 0.3, 0.3)
        if not f["final"]:
            ep = epiano(chord, beat * 2.6)
            add(inst, ep, t0, 0.55, -0.1)
            add(inst, epiano(chord[1:], beat * 1.4), t0 + 2.5 * beat + sw, 0.32, 0.15)
            add(send, ep, t0, 0.2)
        if groove:
            t = tvec(beat * 1.8)
            bs = np.sin(2 * np.pi * hz(root) * t) * np.minimum(1, t / 0.01) * np.exp(-t * 1.2)
            add(inst, bs, t0, 0.55)
            add(inst, bs[: int(SR * beat * 0.9)], t0 + 2.5 * beat + sw, 0.4)
        if f["B"] or f["drop"]:
            for s, ln, m in CHILL_MEL[b % 4]:
                x = bell(m + tr - 12, ln * step + 0.3)
                add(inst, lp(x, 4000), t0 + s * step + (sw if s % 2 else 0), 0.18 if f["B"] else 0.26, 0.2)
                add(send, x, t0 + s * step, 0.15)
        if f["final"]:
            add(inst, epiano(chord, 3.5), t0, 0.6)
    add(drums, vinyl(dur + 2), 0, 1.0)
    out = _finish(drums, inst, send, kicks, N, dur, 0.25)
    out = np.stack([lp(c, 7000) for c in out])
    return out, sec, bar


# ================================================================ CUTE
def marimba(m, dur=0.4):
    t = tvec(dur)
    f = hz(m)
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 30)) * np.exp(-t * 9)


def pizz(m, dur=0.25):
    t = tvec(dur)
    f = hz(m)
    x = saw(f, t) * 0.6 + np.sin(2 * np.pi * f * t) * 0.4
    return lp(x, 2200) * np.exp(-t * 16) * np.minimum(1, t / 0.002)


CUTE_PROG = [([60, 64, 67], 36), ([59, 62, 67], 43), ([60, 64, 69], 45), ([60, 65, 69], 41)]
CUTE_MEL = [[(0, 2, 79), (2, 2, 76), (4, 2, 79), (6, 2, 84), (8, 4, 83), (12, 4, 79)],
            [(0, 2, 79), (2, 2, 74), (4, 2, 79), (6, 2, 83), (8, 4, 81), (12, 4, 79)],
            [(0, 2, 76), (2, 2, 72), (4, 2, 76), (6, 2, 81), (8, 4, 79), (12, 4, 76)],
            [(0, 2, 77), (2, 2, 81), (4, 2, 84), (6, 2, 81), (8, 4, 79), (12, 2, 76), (14, 2, 74)]]


def music_cute(tl, dur):
    bpm = tl.music.get("bpm") or 132
    tr = int(tl.music.get("transpose", 0))
    beat = 60 / bpm
    bar, step = 4 * beat, beat / 4
    N = int(SR * (dur + 3))
    sec = sections(tl, bar, dur)
    drums, inst, send = np.zeros((2, N)), np.zeros((2, N)), np.zeros((2, N))
    K, C = kick(), clap()
    shaker = lambda: hp(RNG.standard_normal(int(0.07 * SR)), 6000) * np.exp(-np.arange(int(0.07 * SR)) / SR * 50) * 0.3
    kicks = []
    for b in range(sec["end"] + 1):
        chord, root = CUTE_PROG[b % 4]
        chord = [n + tr for n in chord]
        root += tr
        f = _flags(b, sec)
        t0 = b * bar
        groove = not (f["intro"] or f["final"])
        if groove:
            for q in (0, 2):
                add(drums, K, t0 + q * beat, 0.55)
                kicks.append(t0 + q * beat)
            for q in (1, 3):
                add(drums, C, t0 + q * beat, 0.4)
            for s in range(0, 16, 2):
                add(drums, shaker(), t0 + s * step + step, 0.35, 0.4)
        if not f["final"]:
            arp = chord + [chord[0] + 12]
            for s in range(0, 16, 2):
                add(inst, marimba(arp[(s // 2) % 4] + 12, 0.35), t0 + s * step, 0.3, -0.2)
            for q in range(4):
                add(inst, pizz(root + 12 + (7 if q % 2 else 0)), t0 + q * beat, 0.45, 0.1)
        if f["B"] or f["drop"]:
            for s, ln, m in CUTE_MEL[b % 4]:
                x = bell(m + tr, 0.4)
                add(inst, x, t0 + s * step, 0.22 if f["B"] else 0.3, 0.25)
                add(send, x, t0 + s * step, 0.12)
        if f["intro"] or f["outro"]:
            add(inst, pad(chord, bar + 0.05, 1600), t0, 0.35)
        if f["final"]:
            add(inst, pluck(chord, 2.5, 3000), t0, 0.6)
            add(send, crash(), t0, 0.2)
    for b in sorted({sec["intro"], sec["drop"]}):
        add(drums, crash(), b * bar, 0.35)
    return _finish(drums, inst, send, kicks, N, dur, 0.4), sec, bar


# ================================================================ ZEN (동양풍 시네마틱: 가야금·대금·장구·북)
# MUSIC['arc'] = [(원본 시각, 단계)] 로 장면마다 에너지를 지정한다. 단계는 가장 가까운 마디 경계로 맞춰진다.
#   calm  : 패드 + 드문 가야금 + 대금 선율          flow  : 가야금 8분 아르페지오 + 북 + 장구 한두 점
#   pulse : 장구 장단 + 첼로 오스티나토 + 대금        peak  : 북(타이코)·합창·현 16분·가야금 두 대·대금 높은 선율
#   build : 북 크레셴도 + 가야금 상행 + 라이저        hush  : calm 보다 더 비운 겨울 같은 공간
#   finale: 큰 타격 + 가야금 글리산도 + 합창 화음 → 여운
ZEN_PROG = [([62, 65, 69], 38), ([58, 62, 65], 34), ([60, 65, 69], 41), ([60, 64, 67], 36)]  # Dm Bb F C
ZEN_ARP = [[62, 65, 69, 74, 77], [58, 62, 65, 70, 74], [60, 65, 69, 72, 77], [60, 64, 67, 72, 79]]
ZEN_MEL = [[(0, 12, 69), (12, 4, 72)], [(0, 8, 74), (8, 6, 72), (14, 2, 69)],
           [(0, 6, 69), (6, 2, 67), (8, 8, 65)], [(0, 12, 67), (12, 4, 69)]]
ZEN_PEAK = [[(0, 6, 74), (6, 2, 77), (8, 8, 81)], [(0, 4, 79), (4, 4, 77), (8, 8, 74)],
            [(0, 6, 77), (6, 2, 74), (8, 4, 72), (12, 4, 74)], [(0, 10, 79), (10, 6, 77)]]
ZEN_LEVELS = ("calm", "flow", "pulse", "build", "peak", "hush", "finale")


def _zen_bars(tl, bar, n, sec):
    arc = tl.music.get("arc")
    if not arc:  # 기본: 섹션 구조에서 만든다
        arc = [(0, "calm"), (sec["intro"] * bar, "flow"), (sec["mid"] * bar, "pulse"), (sec["build"] * bar, "build"),
               (sec["drop"] * bar, "peak"), (sec["outro"] * bar, "finale")]
    off = tl.music.get("start") or 0.0
    lv, start = [], []
    for b in range(n + 1):
        cur, b0 = arc[0][1], 0
        for ta, name in arc:
            if name not in ZEN_LEVELS:
                raise ValueError(f"MUSIC['arc'] 단계는 {ZEN_LEVELS} 중 하나: {name!r}")
            k = int(round((ta - off) / bar))
            if k <= b:
                cur, b0 = name, k
        lv.append(cur)
        start.append(b0)
    return lv, start


def music_zen(tl, dur):
    bpm = tl.music.get("bpm") or 80
    tr = int(tl.music.get("transpose", 0))
    beat = 60 / bpm
    bar, step = 4 * beat, beat / 4
    N = int(SR * (dur + 6))
    sec = sections(tl, bar, dur)
    nb = int(dur // bar) + 1
    lv, b0s = _zen_bars(tl, bar, nb, sec)
    drums, inst, send = np.zeros((2, N)), np.zeros((2, N)), np.zeros((2, N))
    BUK, BUKs, TOM = taiko(110, 50, 4.5, 1.0), taiko(150, 72, 9, 0.5), taiko(230, 140, 12, 0.35)
    KUNG, DEOK, GHOST = janggu("kung"), janggu("deok"), janggu("ghost")
    kicks = []
    fin_done = False
    for b in range(nb):
        L, t0 = lv[b], b * bar
        rel = b - b0s[b]  # 섹션 안에서 몇 번째 마디
        ci = rel % 4
        chord, root = ZEN_PROG[ci]
        chord = [n + tr for n in chord]
        root += tr
        arp = [n + tr for n in ZEN_ARP[ci]]
        first = rel == 0 and b > 0 and lv[b - 1] != L
        if L == "finale" and not fin_done:  # ---- 피날레 타격 (한 번)
            fin_done = True
            add(drums, impact_hit(), t0, 0.9)
            add(drums, BUK, t0, 1.0)
            add(send, crash(), t0, 0.22)
            add(inst, sfx_gliss_up(), t0 - 0.35, 0.5, 0.2)
            ch = choir(chord + [chord[0] + 12], bar * 2.5)
            add(inst, ch, t0, 0.55)
            add(send, ch, t0, 0.35)
            add(inst, pad([root, root + 12, root + 19], bar * 3, 700), t0, 0.5)
            add(inst, daegeum(74 + tr, bar * 2.2, 0.45), t0 + beat, 0.42, 0.15)
            add(send, daegeum(74 + tr, bar * 2.2, 0.45), t0 + beat, 0.3)
            for k, m in enumerate((74, 69, 65, 62)):
                g = gayageum(m + tr, 2.4, 0.4, 0.0, 0.3, k)
                add(inst, g, t0 + bar * 1.5 + k * beat * 1.5, 0.35, -0.3 + 0.2 * k)
            continue
        if L == "finale":
            continue
        # ---- 패드·저음
        if L in ("calm", "hush", "flow", "pulse"):
            add(inst, pad(chord, bar + 0.4, 650 if L == "hush" else 900), t0, 0.38 if L != "hush" else 0.3)
            add(send, pad(chord, bar + 0.4, 900), t0, 0.15)
        if L in ("flow", "pulse", "peak", "build"):
            add(inst, pad([root, root + 12], bar + 0.2, 380), t0, 0.5)
        # ---- 가야금
        if L in ("calm", "hush"):
            pat = [(0, 3), (6, 2), (10, 4)] if L == "calm" else [(0, 4), (10, 3)]
            for s, i in pat:
                g = gayageum(arp[i] + (12 if L == "hush" else 0), 2.2, 0.35, 0.0, 0.35 if s == 0 else 0.0, s)
                add(inst, g, t0 + s * step, 0.38 if L == "calm" else 0.26, 0.3 - 0.1 * i)
                add(send, g, t0 + s * step, 0.25)
        elif L in ("flow", "pulse"):
            seq = [0, 2, 1, 3, 2, 4, 3, 1]
            for e in range(8):
                g = gayageum(arp[seq[e]], 1.3, 0.45 + 0.1 * (L == "pulse"), 0.0, 0.25 if e == 0 else 0.0, e)
                add(inst, g, t0 + e * 2 * step, 0.34 if e % 2 == 0 else 0.26, -0.25 + 0.1 * (e % 3))
                add(send, g, t0 + e * 2 * step, 0.12)
            if L == "pulse":
                for s in (13, 14, 15):
                    add(inst, gayageum(arp[(s - 12) % 5] + 12, 0.6, 0.6, 0.0, 0.0, s), t0 + s * step, 0.2, 0.35)
        elif L in ("peak", "build"):
            seq = [0, 1, 2, 3, 4, 3, 2, 1]
            for s in range(16):
                m = arp[seq[s % 8]] + (12 if L == "peak" and s >= 8 and ci % 2 else 0)
                add(inst, gayageum(m, 0.9, 0.6, 0.0, 0.0, s), t0 + s * step, 0.26 if s % 4 else 0.34, -0.35)
                if L == "peak":
                    add(inst, gayageum(m + 12, 0.7, 0.7, 0.0, 0.0, s + 20), t0 + s * step + 0.012, 0.13, 0.4)
        # ---- 북·장구
        if L == "flow":
            add(drums, BUK, t0, 0.42)
            add(drums, KUNG, t0 + 8 * step, 0.35)
            add(drums, DEOK, t0 + 12 * step, 0.22, 0.2)
            kicks.append(t0)
        elif L == "pulse":
            add(drums, BUK, t0, 0.55)
            for s in (6, 10):
                add(drums, KUNG, t0 + s * step, 0.42)
            for s in (4, 8, 12, 14):
                add(drums, DEOK, t0 + s * step, 0.3, 0.25)
            for s in (2, 15):
                add(drums, GHOST, t0 + s * step, 0.3, 0.25)
            kicks += [t0]
        elif L == "peak":
            for s in TAIKO_B:
                add(drums, BUK if s in (0, 8) else BUKs, t0 + s * step, 0.9 if s in (0, 8) else 0.55, 0.15 * math.sin(s))
            for s in (4, 12):
                add(drums, DEOK, t0 + s * step, 0.4, 0.25)
            for s in (2, 6, 10, 14, 15):
                add(drums, GHOST, t0 + s * step, 0.35, 0.25)
            if rel % 4 == 3:
                for s in (12, 13, 14, 15):
                    add(drums, TOM, t0 + s * step, 0.35 + 0.1 * (s - 12), -0.3 + 0.2 * (s - 12))
            kicks += [t0, t0 + 8 * step]
            if first:
                add(drums, impact_hit(), t0, 0.7)
                add(send, crash(), t0, 0.2)
        elif L == "build":
            k = rel
            nbld = 1
            while b + nbld < nb and lv[b + nbld] == "build":
                nbld += 1
            tot = rel + nbld
            for s in range(0, 16, 2 if (k + 1) < tot else 1):
                prog = (k * 16 + s) / (tot * 16)
                add(drums, BUKs if s % 4 else BUK, t0 + s * step, 0.3 + 0.55 * prog)
            if (k + 1) == tot:
                add(drums, noise_riser(bar, 300, 8000), t0, 0.35)
        # ---- 첼로 오스티나토 / 합창
        if L in ("pulse", "peak", "build"):
            sub = 2 if L == "pulse" else 1
            pat = [0, 0, 7, 0, 12, 0, 7, 3]
            third = 3 if ci == 0 else 4
            for s in range(0, 16, sub):
                p = pat[(s // sub) % 8]
                m = root + 12 + (third if p == 3 else p)
                add(inst, stac(m, 0.14, 1500 if L == "pulse" else 2400), t0 + s * step, 0.22 if sub == 1 else 0.28, -0.2)
        if L == "peak":
            ch = choir(chord + [chord[0] + 12], bar + 0.4)
            add(inst, ch, t0, 0.36)
            add(send, ch, t0, 0.3)
        # ---- 대금 선율
        mel = None
        if L in ("calm", "flow", "pulse") and ci in (0, 2):
            mel, g = ZEN_MEL, 0.34 if L == "calm" else 0.3
            mel_bars = (ci, ci + 1)
        elif L == "hush" and ci == 0:
            mel, g, mel_bars = ZEN_MEL, 0.26, (0, 1)
        elif L == "peak":
            mel, g, mel_bars = ZEN_PEAK, 0.42, (ci,)
        if mel:
            for j, mb in enumerate(mel_bars):
                for s, ln, m in mel[mb]:
                    d = daegeum(m + tr, ln * step + 0.05, 0.4)
                    add(inst, d, t0 + j * bar + s * step, g, 0.1)
                    add(send, d, t0 + j * bar + s * step, 0.3)
    for b in range(1, nb):  # 단계가 바뀌는 마디: 가벼운 심벌 / build 직후 큰 타격
        if lv[b] != lv[b - 1] and lv[b] in ("flow", "pulse") and lv[b - 1] in ("calm", "hush"):
            add(send, crash(), b * bar, 0.08)
    # 단계별 음량 — 마스터가 전체를 정규화하므로 조용한 단계를 확실히 낮춰야 절정이 산다
    gains = dict(calm=0.42, hush=0.38, flow=0.6, pulse=0.75, build=0.85, peak=1.0, finale=1.0)
    xs, ys = [0.0], [gains[lv[0]]]
    for b in range(1, nb + 1):  # 마디 경계에서 0.35초 동안 다음 단계 음량으로
        xs += [b * bar, b * bar + 0.35]
        ys += [gains[lv[b - 1]], gains[lv[b]]]
    env = np.interp(np.arange(N) / SR, xs, ys)
    for buf in (drums, inst, send):
        buf *= env
    return _finish(drums, inst, send, kicks, N, dur, 0.18), sec, bar


def sfx_gliss_up():
    from music import sfx_gliss
    return sfx_gliss(True)


STYLES = {"epic": music_epic, "chill": music_chill, "cute": music_cute, "zen": music_zen}
