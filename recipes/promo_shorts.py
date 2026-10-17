"""레시피: 30초 세로 쇼츠 (광고 몽타주) — 가로 원본을 1080x1920 으로, 장면 하나 = 한 마디(96 BPM, 2.5초).

사용법: 이 파일을 영상 옆에 복사(예: shorts.py) → SEGMENTS·PANS·타이포 문구·CLEANUP 을 채움 → build.py shorts.py --preview-out 으로 확인.
  - SEGMENTS 의 출력 길이 합 = 영상 길이. 전환(원본 크로스페이드) 구간은 0.2~0.3초로 압축하고 그 가운데가 마디 경계(2.5의 배수)에 오게 한다.
  - 타이포 시각은 at(출력초) 로 쓴다 (빨리감기 구간에서도 정확).
  - 기본값은 사계 수묵 애니메이션(116초 → 30초)으로 검증한 값이다. 다른 영상에서는 반드시 다시 측정한다.
"""
from remap import Remap  # 엔진 scripts 폴더가 경로에 있다 (배속 역산용)

CANVAS = (1080, 1920)
PROFILE = "promo"
SRC = "film.mp4"
OUTPUT = "output/promo_shorts.mp4"
OUTPUT_SIZE = (1080, 1920)
BUILD_DIR = "build_shorts"
QUALITY = 18
FADE_OUT = 0.8
BACKDROP = dict(kind="blur", tint=(240, 233, 216), amount=0.5)   # 흐린 확대 배경 + 종이색
SPEED_RAMP = 0.06

# ---------------------------------------------------------------- 편집 구간: (원본 시작, 원본 끝, 출력 길이) — 이어 붙여 박자에 맞춘다
BEAT = 60 / 96
SEGMENTS = [
    (1.0, 4.6, 2.5),       # 0.0  빈 종이에 산수가 번짐 (훅 카피)
    (4.6, 10.4, 2.35),     # 2.5  KOREA (마디 1 타격)
    (10.4, 13.0, 0.3),     #      먹물 → 5.0
    (13.0, 25.3, 2.25),    # 5.15 동해 일출 (타임랩스)
    (25.3, 27.4, 0.2),     #      플래시 → 7.5
    (27.4, 36.6, 2.3),     # 7.6  벚꽃
    (36.6, 38.6, 0.2),     #      먹물 → 10.0
    (38.6, 51.4, 2.3),     # 10.1 여름 호수
    (51.4, 53.8, 0.2),     #      플래시 → 12.5
    (53.8, 62.8, 2.3),     # 12.6 폭포
    (62.8, 65.0, 0.2),     #      먹물 → 15.0 (절정)
    (65.0, 77.8, 2.3),     # 15.1 가을 산사
    (77.8, 80.3, 0.2),     #      플래시 → 17.5
    (80.3, 88.8, 2.3),     # 17.6 달빛 억새
    (88.8, 91.2, 0.2),     #      먹물 → 20.0
    (91.2, 103.8, 2.3),    # 20.1 겨울 산사
    (103.8, 105.0, 0.2),   #      먹물 → 22.5
    (105.0, 109.4, 2.4),   # 22.6 병풍이 펼쳐짐
    (109.4, 114.6, 5.2),   # 25.0 엔드 카드 (피날레 타격)
]
TRIM = (SEGMENTS[0][0], SEGMENTS[-1][1])


def _solve():
    """출력 길이에 맞는 배속을 구하고, 램프로 생기는 오차를 몇 번 되먹여 보정한다."""
    rates = [(b - a) / d for a, b, d in SEGMENTS]
    for _ in range(6):
        rm = Remap(*TRIM, [(a, b, r) for (a, b, _), r in zip(SEGMENTS, rates)], ramp=SPEED_RAMP)
        rates = [r * (rm.out(b) - rm.out(a)) / d for (a, b, d), r in zip(SEGMENTS, rates)]
    return rates


SPEED = [(a, b, r, None) for (a, b, _), r in zip(SEGMENTS, _solve())]
CUT = [(a + b) / 2 for a, b, d in SEGMENTS if d <= 0.3]   # 전환 중심(원본 시각)
INK_CUTS, FLASH_CUTS = [CUT[i] for i in (0, 2, 4, 6, 7)], [CUT[i] for i in (1, 3, 5)]

# ---------------------------------------------------------------- 원본 한글 글씨 지우기 (가로 광고와 같은 값)
CLEANUP = [
    (4.25, 10.45, (1590, 100, 1845, 672), dict(plate=4.2, mask="box", feather=14)),
    (13.4, 25.1, (1650, 66, 1842, 566), dict(plate=(13.2, 25.15), ref=20.0)),
    (28.2, 36.3, (1650, 66, 1842, 580), dict(plate=(28.0, 36.4), ref=32.0)),
    (39.4, 51.3, (48, 66, 222, 484), dict(plate=(39.25, 51.35), ref=45.0)),
    (54.5, 62.75, (1672, 476, 1838, 800), dict(ref=59.0, radius=9)),
    (65.8, 77.6, (48, 66, 224, 500), dict(plate=(65.7, 77.7), ref=74.0)),
    (81.0, 88.75, (48, 66, 224, 560), dict(plate=(80.95, 88.8), ref=87.0)),
    (92.4, 103.8, (1672, 66, 1842, 562), dict(plate=(92.0, 103.85), ref=99.0)),
    (109.45, 114.6, (540, 862, 1545, 1074), dict(plate=109.45, mask="box", feather=12)),
    (104.0, 114.6, (140, 795, 1780, 827), dict(ink="light", live=True, k=21, thr=40, seal=False, grow=3)),
]

# ---------------------------------------------------------------- 카메라: 띠 레이아웃 ↔ 꽉 찬 세로 크롭 + 패닝
ZF = 1920 / (1080 * 1080 / 1920)          # 16:9 원본이 세로 화면을 꽉 채우는 배율 (≈3.16)
PANS = [  # (원본 시작, 원본 끝, 시작 x, 끝 x, 시작 배율, 끝 배율) — x 는 원본 픽셀
    (13.0, 25.3, 1206, 1206, 1.0, 1.1),    # 해를 가운데 두고 밀기
    (27.4, 36.6, 380, 600, 1.04, 1.04),    # 까치 앉은 가지 → 산자락
    (38.6, 51.4, 700, 1160, 1.02, 1.02),   # 정자 → 나룻배
    (53.8, 62.8, 880, 880, 1.0, 1.12),     # 폭포 밀기
    (65.0, 77.8, 430, 1420, 1.0, 1.0),     # 산사 → 단풍 (빠른 패닝)
    (80.3, 88.8, 1276, 1276, 1.08, 1.0),   # 달에서 빠지기
    (91.2, 103.8, 1320, 620, 1.02, 1.02),  # 학 → 산사
]
SHOTS = [(TRIM[0], 0, "full"), (1.0, 9.0, "full", 1.07)]
for a, b, x0, x1, z0, z1 in PANS:
    SHOTS += [(a - 0.02, 0.02, x0, 540, ZF * z0), (a, b - a, x1, 540, ZF * z1)]
SHOTS += [(104.98, 0.02, "full"), (105.0, 9.0, "full", 1.03)]

# ---------------------------------------------------------------- 타이포 (캔버스 1080x1920, 위아래 안전 여백 260px)
WHITE = (250, 247, 238)
DARK_HALO = ((14, 14, 18), 22, 0.65)


def at(sec):
    """출력 시각(초) → (원본 시각, 오프셋) 표기. 빨리감기 구간에서도 출력 기준으로 정확하다."""
    return (TRIM[0], sec)


BAR = 2.5
TYPE = [
    (at(0.15), at(2.35), "line", dict(text="Four seasons.", pos=(540, 400), size=78, italic=True, stagger=0.12)),
    (at(1.0), at(2.35), "line", dict(text="One masterpiece.", pos=(540, 1400), size=78, italic=True, stagger=0.12)),
    (at(2.5), at(4.85), "hero", dict(text="KOREA", pos=(540, 420), size=176, tracking=(1.1, 0.3), seal="錦繡江山",
                                     seal_size=78, seal_t=0.6, sub="Land of Embroidered Rivers & Mountains", sub_size=32,
                                     rule=False)),
    (at(3.1), at(4.85), "line", dict(text="GEUMSU  ·  GANGSAN", pos=(540, 1380), size=34, font="serif", tracking=0.3, sfx=[])),
]
for k, (name, seal) in enumerate((("SPRING", "春"), ("SUMMER", "夏"), ("AUTUMN", "秋"), ("WINTER", "冬"))):
    tc = 2 * BAR * (k + 1)                                         # 먹물이 화면을 덮는 순간: 5, 10, 15, 20초
    TYPE.append((at(tc - 0.03), at(tc + 1.05), "slam", dict(text=name, pos=(540, 900), size=170, seal=seal, color=WHITE,
                                                         halo=DARK_HALO, tracking=0.2)))
SCENE_TITLES = [  # (출력 시작, 출력 끝, 계절, 낙관, 제목, (글자색, 후광) | None)
    (6.0, 7.4, "SPRING", "春", "Sunrise over the East Sea", None),
    (7.62, 9.88, "SPRING", "春", "Hills in Blossom", None),
    (11.0, 12.4, "SUMMER", "夏", "Lakes of Stillness", None),
    (12.62, 14.88, "SUMMER", "夏", "The Song of Waterfalls", None),
    (16.0, 17.4, "AUTUMN", "秋", "Crimson Peaks, Quiet Temples", None),
    (17.62, 19.88, "AUTUMN", "秋", "Silver Grass under the Moon", (WHITE, ((18, 22, 40), 18, 0.55))),
    (21.0, 22.4, "WINTER", "冬", "A Hush of Snow", None),
]
for a, b, kicker, seal, title, look in SCENE_TITLES:
    opt = dict(kicker=kicker, title=title, seal=seal, pos=(80, 300), align="left", kicker_size=28, size=56, seal_size=92,
               veil=(0.7, 110), pace=0.55)
    if look:
        opt.update(color=look[0], halo=look[1], veil=(0.3, 90), veil_color=(20, 24, 40))
    TYPE.append((at(a), at(b), "chapter", opt))
TYPE += [
    (at(25.0), (114.6, 0), "hero", dict(text="KOREA", pos=(540, 420), size=176, tracking=(1.1, 0.3), seal="錦繡江山",
                                        seal_size=78, seal_t=0.6, sub="Every season, a masterpiece.", sub_size=36, rule=False)),
    (at(25.9), (114.6, 0), "line", dict(text="FOUR SEASONS  ·  ONE PENINSULA", pos=(540, 1380), size=32, font="serif",
                                        tracking=0.22, sfx=[])),
]

# ---------------------------------------------------------------- 빛·전환·파티클
TRACKS = {
    "sun": dict(keys=[(14.5, (1150, 652, 100, 100)), (16.5, (1151, 597, 100, 100)), (18.5, (1153, 542, 100, 100)),
                      (20.5, (1154, 505, 100, 100)), (25.3, (1157, 496, 100, 100))]),
    "moon": dict(keys=[(80.3, (1222, 297, 100, 100)), (86.0, (1226, 254, 100, 100)), (88.8, (1226, 238, 100, 100))]),
}
GLOWS = [(14.0, 25.4, "@sun", dict(radius=200, color=(255, 150, 80), strength=0.6)),
         (80.3, 89.0, "@moon", dict(radius=260, color=(205, 220, 255), strength=0.35, flare=False))]
INK = [(t, dict(dur=0.9)) for t in INK_CUTS]
FLASH = [(t, (255, 252, 240), 0.75, 0.3) for t in FLASH_CUTS]

PARTICLES = [
    (16.0, 25.3, "sparkle", dict(at=(1206, 820), rate=14, jitter=150, size=(14, 30))),
    (27.4, 36.8, "petals", dict(at="screen", area=(0, -40, 1080, 1300), rate=18)),
    (38.6, 51.6, "fireflies", dict(at="screen", area=(0, 1150, 1080, 1700), rate=8, alpha=0.85)),
    (53.8, 63.0, "bokeh", dict(at=(880, 830), rate=5, jitter=160, alpha=0.55, palette=[6])),
    (65.0, 78.0, "leaves", dict(at="screen", area=(0, -40, 1080, 1300), rate=14)),
    (80.3, 89.0, "fireflies", dict(at="screen", area=(0, 1100, 1080, 1650), rate=8, alpha=0.9)),
    (91.2, 104.6, "snow", dict(at="screen", area=(0, -40, 1080, 1500), rate=60, size=(12, 26))),
    (109.6, 110.0, "sparkle", dict(at=(960, 540), burst=40, jitter=420)),
]
for _i, _p in enumerate(PARTICLES[:-1]):   # 컷마다 파티클도 함께 끊기
    PARTICLES[_i] = (_p[0], _p[1], _p[2], dict(_p[3], clip=True))

# ---------------------------------------------------------------- 사운드: zen 96 BPM, 마디(2.5초)마다 장면
MUSIC = dict(style="zen", bpm=96, volume=1.0,
             arc=[(1.0, "build"), (4.6, "peak"), (CUT[0], "pulse"), (CUT[3], "build"), (CUT[4], "peak"),
                  (CUT[6], "hush"), (CUT[7], "build"), (109.4, "finale")])
SFX = [(4.6, "gliss", 0.7)] + [(t, "whoosh", 0.5) for t in FLASH_CUTS] + [
    (14.0, "waves:2.5", 0.3), (28.0, "birds:2.5", 0.4), (54.0, "water:2.5", 0.4), (66.0, "temple_bell:3", 0.5),
    (81.0, "wind:2.5", 0.35)]
