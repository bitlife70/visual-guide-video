"""레시피: 광고·홍보·여행 필름 (자연·도시·문화·브랜드) — 자막·성우 없이 광고 타이포 + 음악으로.

사용법: 이 파일을 영상 옆에 timeline.py 로 복사 → [1. 채울 값] 만 채움 → build.py --preview-out 으로 확인 → 미세 조정.
시각은 원본 영상 초, 좌표는 원본 픽셀 (analyze.py 시트와 crops.py 눈금으로 측정). 타이포 위치(pos)는 1920x1080 캔버스.
기본값은 사계절 수묵 애니메이션(116초 → 85초 광고)으로 검증한 값이다. 다른 영상에서는 반드시 다시 측정한다.

이야기 구조 (광고 문법)
  오프닝 카피 2줄(짧게, 이탤릭) → 히어로 타이틀(자간이 모이며 등장 + 낙관) → 장면마다 챕터 타이포(낙관이 '쾅')
  → 큰 장(계절·지역)이 바뀔 때 먹물 번짐 전환 → 에너지가 올라가는 음악(calm → flow → pulse → build → peak → hush → finale)
  → 엔드 카드(브랜드 + 태그라인), 마지막 프레임 정지

핵심 요령
  - 원본에 다른 언어 글씨가 박혀 있으면 CLEANUP 으로 지운다. 글씨가 '없는' 프레임(plate)을 글씨가 나타나기 0.4초 이상 전/사라진 뒤에서
    고른다 (페이드 중인 프레임엔 희미한 글씨가 남아 있다 → 대비를 키운 크롭으로 확인). 배경이 움직이면 자동 이동 보정,
    안개처럼 형태가 바뀌는 배경은 plate 없이 인페인트 + 그 자리에 챕터 타이포를 veil 과 함께 올린다.
  - 장면 전환(먹물 번짐 중심 시각)이 마디 경계(80 BPM = 3초)에 떨어지도록 SPEED 배속을 조정한다. tl.load 로 out 시각을 출력해 맞춘다.
  - 느린 그림·풍경 영상은 1.5~2.4배로 줄여도 자연스럽다. 결정적 장면(전개되는 병풍·일출)은 0.75~1배.
"""

# ============================================================ 1. 채울 값
PROFILE = "promo"
SRC = "film.mp4"
OUTPUT = "output/promo_film.mp4"
TRIM = (0.6, 114.6)

OPENING = [((0.75, 2.35), "Four seasons."), ((2.45, 4.85), "One masterpiece.")]   # (원본 구간, 문구)
OPENING_Y = 400
HERO = dict(range=(5.0, 10.35), text="KOREA", pos=(1210, 300), size=176, seal="錦繡江山",
            sub=["Land of Embroidered Rivers & Mountains", "GEUMSU  ·  GANGSAN"])
END = dict(start=109.55, hold=2.6, text="KOREA", pos=(960, 938), size=104, seal="錦繡江山",
           sub="Every season, a masterpiece.")

# 장면: 원본 구간(시작, 끝)·배속·챕터 문구·낙관·문구 위치·카메라가 다가갈 곳·파티클·에너지·배경 소리
SCENES = [
    dict(span=(16.0, 25.3), speed=1.6, text=(14.2, 24.6), kicker="SPRING", title="Sunrise over the East Sea", seal="春",
         pos=(1830, 160), focus=(1206, 560, 1.12), particles=[("sparkle", dict(at="screen", area=(1090, 680, 1330, 960), rate=9))],
         energy="flow", ambience=("waves:9", 0.35)),
    dict(span=(27.4, 36.6), speed=1.58, text=(28.6, 36.0), kicker="SPRING", title="Hills in Blossom", seal="春",
         pos=(1830, 160), focus=(640, 470, 1.1), particles=[("petals", dict(rate=7))], ambience=("birds:7", 0.45)),
    dict(span=(38.6, 51.4), speed=2.37, text=(39.8, 50.8), kicker="SUMMER", title="Lakes of Stillness", seal="夏",
         pos=(90, 160), align="left", focus=(1150, 640, 1.1), energy="pulse",
         particles=[("fireflies", dict(at="screen", area=(0, 640, 1920, 930), rate=4, alpha=0.8))]),
    dict(span=(53.8, 62.8), speed=1.8, text=(54.9, 62.4), kicker="SUMMER", title="The Song of Waterfalls", seal="夏",
         pos=(1830, 500), veil=(0.85, 150), focus=(880, 600, 1.12), energy="build", ambience=("water:6", 0.45),
         particles=[("bokeh", dict(at="screen", area=(700, 640, 1060, 940), rate=2.2, alpha=0.55, palette=[6]))]),
    dict(span=(65.0, 77.8), speed=1.79, text=(66.2, 77.2), kicker="AUTUMN", title="Crimson Peaks, Quiet Temples", seal="秋",
         pos=(90, 160), align="left", focus=(760, 560, 1.08), particles=[("leaves", dict(rate=6))], energy="peak",
         ambience=("temple_bell", 0.7)),
    dict(span=(80.3, 88.8), speed=1.5, text=(81.4, 88.5), kicker="AUTUMN", title="Silver Grass under the Moon", seal="秋",
         pos=(90, 160), align="left", color=(250, 247, 238), halo=((18, 22, 40), 18, 0.5), focus=(1276, 380, 1.1),
         particles=[("fireflies", dict(at="screen", area=(0, 560, 1920, 900), rate=3.5, alpha=0.85))], ambience=("wind:6", 0.4)),
    dict(span=(91.2, 103.8), speed=1.94, text=(92.7, 103.5), kicker="WINTER", title="A Hush of Snow", seal="冬",
         pos=(1830, 160), focus=(1250, 700, 1.08), particles=[("snow", dict(rate=26, size=(12, 24)))], energy="hush",
         ambience=("temple_bell", 0.35)),
]
INK_AT = [(11.2, (1210, 300)), (37.5, "center"), (63.7, (880, 560)), (90.0, (1276, 300)), (105.0, "center")]  # 큰 장 전환
SLOW = [(0.6, 3.0, 0.6), (105.0, 109.4, 0.75)]          # 천천히 보여줄 구간 (첫 번짐, 피날레 전개)
FAST = [(12.6, 16.0, 2.0)]                              # 장면 밖 군더더기 구간
GLOW_TRACKS = {                                         # 빛나는 대상 (해·달·조명): 키프레임 (원본 시각, (x, y, w, h))
    "sun": [(14.5, (1150, 652, 100, 100)), (18.5, (1153, 542, 100, 100)), (22.0, (1155, 497, 100, 100)), (25.3, (1157, 496, 100, 100))],
    "moon": [(80.3, (1222, 297, 100, 100)), (86.0, (1226, 254, 100, 100)), (88.8, (1226, 238, 100, 100))],
}
GLOWS = [(14.6, 25.4, "@sun", dict(radius=230, color=(255, 150, 80), strength=0.55)),
         (80.3, 89.0, "@moon", dict(radius=300, color=(205, 220, 255), strength=0.32, flare=False))]
CLEANUP = []                                            # 원본 글씨 지우기 (promo.py 설명 참고). 예:
# CLEANUP = [(13.4, 25.1, (1650, 66, 1842, 566), dict(plate=(13.2, 25.15), ref=20.0))]
MUSIC_START_LEVEL = "calm"
FINALE_BUILD = 105.0                                    # 이 시각부터 북 크레셴도 → END["start"] 에 피날레 타격

# ============================================================ 2. 레시피 (보통 고칠 필요 없음)
OUTPUT_SIZE = (1920, 1080)
QUALITY = 19
FADE_OUT = 1.4
SEASON = dict(kicker_size=26, size=54, seal_size=88)

SPEED = [(a, b, r, None) for a, b, r in SLOW + FAST] + [(s["span"][0], s["span"][1], s["speed"], None) for s in SCENES]
SPEED.sort()
FREEZE = [(TRIM[1] - 0.05, END["hold"], None, dict(look="none", sfx=False))] if END.get("hold") else []   # 엔드 카드 유지
END_T1 = (TRIM[1] - 0.05, END["hold"]) if FREEZE else TRIM[1]

TYPE = [(a, b, "line", dict(text=s, pos=(960, OPENING_Y), size=74, italic=True, stagger=0.2)) for (a, b), s in OPENING]
TYPE.append((*HERO["range"], "hero", dict({k: v for k, v in HERO.items() if k != "range"}, seal_size=92, seal_t=1.3, sub_size=40)))
for s in SCENES:
    opt = dict(kicker=s["kicker"], title=s["title"], seal=s.get("seal"), pos=s["pos"], align=s.get("align", "right"), **SEASON)
    for k in ("color", "halo", "veil"):
        if k in s:
            opt[k] = s[k]
    TYPE.append((*s["text"], "chapter", opt))
TYPE.append((END["start"], END_T1, "hero", dict(text=END["text"], pos=END["pos"], size=END["size"], tracking=(0.9, 0.42),
                                               seal=END.get("seal"), seal_size=64, seal_t=1.2, sub=END["sub"], sub_size=34,
                                               rule=False)))

TRACKS = {k: dict(keys=v) for k, v in GLOW_TRACKS.items()}
SHOTS = [(TRIM[0], 0, "full")]
for s in SCENES:
    fx_, fy, z = s["focus"]
    SHOTS.append((s["span"][0], s["span"][1] - s["span"][0], fx_, fy, z))
for t, _ in INK_AT:
    SHOTS.append((t, 0.3, "full"))                       # 먹물이 화면을 덮은 동안 원위치
SHOTS.sort(key=lambda x: x[0])
LETTERBOX = dict(ratio=2.39, range=(OPENING[-1][0][0] + 0.15, INK_AT[-1][0] + 0.6), fade=1.0)
INK = [(t, dict(dur=1.7, at=at)) for t, at in INK_AT]

PARTICLES = []
for s in SCENES:
    for kind, opt in s.get("particles", []):
        PARTICLES.append((s["span"][0], s["span"][1] + 0.4, kind, opt))
        if kind in ("petals", "leaves"):                 # 처음부터 화면에 떠 있게
            PARTICLES.append((s["span"][0], s["span"][0] + 2.5, kind, dict(at="screen", area=(0, 100, 1920, 700), rate=9)))

arc = [(TRIM[0], MUSIC_START_LEVEL)]
level = MUSIC_START_LEVEL
for s in SCENES:                                         # 에너지가 바뀌는 곳: 가까운 먹물 전환이 있으면 그 시각
    if s.get("energy") and s["energy"] != level:
        level = s["energy"]
        near = min((t for t, _ in INK_AT), key=lambda t: abs(t - s["span"][0]))
        arc.append((near if abs(near - s["span"][0]) < 5 else s["span"][0], level))
arc += [(FINALE_BUILD, "build"), (END["start"], "finale")]
MUSIC = dict(style="zen", bpm=80, volume=0.95, arc=arc)
SFX = [(HERO["range"][0], "gliss", 0.6)] + [(s["span"][0] + 0.4, *s["ambience"]) for s in SCENES if s.get("ambience")]
