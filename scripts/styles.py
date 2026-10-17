"""BGM 스타일 (MUSIC['style']).

  pop   : 126 BPM 일렉트로 팝 (music.py, 화면녹화 기본)
  epic  : 96 BPM 트레일러풍 — 타이코·스타카토 현·브라스 '브람'·합창 패드 (게임 기본, D 단조)
  chill : 82 BPM 로파이 — 일렉피아노·스윙 드럼·바이닐 노이즈 (브이로그 기본)
  cute  : 132 BPM 마림바·피치카토·글로켄 (애니메이션 기본, C 장조)

모든 스타일이 music.sections() 의 섹션 구조(intro/A/B/build/drop/outro)를 따르므로 MUSIC['drop'] 이 동일하게 동작한다.
"""
import math

import numpy as np

from music import (RNG, SR, add, bell, bp, crash, hat, hp, hz, kick, lead, lp, master, noise_riser, pad, pluck, reverb,
                   saw, sections, snare, tvec, clap)


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


STYLES = {"epic": music_epic, "chill": music_chill, "cute": music_cute}
