"""레시피: 화면녹화 워크스루 — 클릭할 때마다 줌인·풍선·화살표, 장면마다 카드와 하이라이트.

사용법: 이 파일을 녹화 옆에 timeline.py 로 복사 → [1. 채울 값] 만 채움 → build.py --preview 로 확인 → 미세 조정.
시각은 원본 영상 초, 좌표는 원본 픽셀.
  클릭 시각: analyze.py 의 switch / big-change 이벤트 start - 0.05
  클릭 좌표: 이벤트 직전 프레임의 마우스 커서 위치 (crops.py --box 로 50px 눈금 확인)

이야기 구조
  인트로 제목 → 전체 구조(핵심 영역 하이라이트) → [클릭마다] 줌인 → 리플·풍선 → 줌아웃 → 바뀐 곳 화살표 → 요약 카드
  → 그 화면의 핵심 내용 하이라이트 → 다음 클릭 … → 요약 아웃트로
레이아웃 규칙 (엔진이 지키지 못하는 것)
  - 카드(우측 중단)와 하이라이트가 같은 시간에 겹치지 않게: 카드가 끝난 뒤 POINTS 를 시작한다.
  - 하이라이트 라벨이 다른 줄을 가리면 배치 "right"(화살표) / "above-right"(표의 행) / "below"(화면 상단 요소).
"""

# ============================================================ 1. 채울 값
PROFILE = "screen"
SRC = "recording.mp4"
OUTPUT = "output/walkthrough.mp4"

TITLE_CHIP = "PRODUCT DEMO"
TITLE_TEXT = "제품 [×] 기능"
TITLE_SUB = "[한 줄]로 요약한 영상 주제"
TITLE_TOKENS = [("🧠", "역할 1"), ("🛠️", "역할 2")]
INTRO_END = 3.3

OVERVIEW = [                            # 인트로 직후 전체 구조 설명: ((x0,y0,x1,y1), 라벨, 색)
    ((22, 783, 382, 810), "🧠 핵심 영역 1", "cyan"),
    ((22, 822, 382, 980), "🚀 핵심 영역 2", "accent"),
]
OVERVIEW_FOCUS = (470, 830, 1.9)        # 전체 구조 설명 때 카메라 (cx, cy, zoom), 없으면 None

CLICKS_IN = [                           # (t, (x, y), 풍선 문구, 바뀐 곳 사각형 | None, 카드 (이모지, 제목, [줄...]) | None)
    (7.55, (198, 838), "🐱 세션 A로 이동", (677, 8, 817, 50), ("🐱", "세션 A", ["무엇을 하는 화면인지", "핵심 포인트"])),
    (13.63, (198, 882), "🐭 세션 B로 이동", (935, 8, 1112, 50), ("🐭", "세션 B", ["무엇을 하는 화면인지"])),
    (23.83, (202, 796), "🧠 처음 화면으로 복귀", None, None),
]
POINTS = [                              # 클릭 사이 강조할 내용: (t0, t1, (x0,y0,x1,y1), 라벨[, 색[, 배치]])
    (25.6, 26.3, (430, 84, 1862, 376), "📋 전체 현황표", "cyan"),
    (26.3, 27.0, (430, 122, 1862, 186), "첫 번째 항목", "accent", "above-right"),
]
SAY = [                                 # 자막 (t0, t1, 문구)
    (3.5, 6.45, "한 화면에서 [여러 작업]이 동시에 진행됩니다"),
    (6.55, 7.9, "하나씩 들여다볼까요? 먼저 [세션 A]로!"),
]
STEPS = [(0.0, "STEP 1 · 전체 구조"), (7.6, "STEP 2 · 세부 투어")]   # HUD 단계 (HUD_ITEMS 가 있을 때)
HUD_ITEMS = []                          # 좌상단 목록: [("🧠", "코디네이터"), ("🐱", "세션 A"), ...] — 클릭과 같은 순서
HUD_ACTIVE = []                         # (t, 활성 인덱스): 클릭 직후 바뀌는 항목
END = 54.5                              # 아웃트로 시작
OUTRO_TITLE = "[핵심 메시지] 한 줄"
OUTRO_STATS = [("⚡", "포인트 1", "설명"), ("📜", "포인트 2", "설명"), ("🚀", "포인트 3", "설명")]
DROP = None                             # 음악 하이라이트 시작 (가장 중요한 공개 직전), None = 70% 지점
NARRATION = None                        # 성우: [(t, "문장")] — --voice edge|sapi 일 때

# ============================================================ 2. 레시피 (보통 고칠 필요 없음)
ZOOM, LEAD, BACK = 2.3, 0.9, 0.3        # 클릭 줌 배율, 클릭 몇 초 전부터 줌, 클릭 후 몇 초 뒤 복귀

TITLE = dict(range=(0.0, INTRO_END), chip=TITLE_CHIP, title=TITLE_TEXT, subtitle=TITLE_SUB, tokens=TITLE_TOKENS)
OUTRO = dict(start=END, chip="🎬 요약", title=OUTRO_TITLE, stats=OUTRO_STATS, footer="")

SHOTS = [(0.0, INTRO_END - 0.1, "full", 1.06)]
if OVERVIEW_FOCUS:
    SHOTS.append((INTRO_END - 0.05, 0.9, *OVERVIEW_FOCUS))
CLICKS, LINKS, CARDS = [], [], []
first = CLICKS_IN[0][0] if CLICKS_IN else END
HIGHLIGHTS = [(INTRO_END + 0.6 + 0.4 * i, first - LEAD - 0.15, rect, label, col, "right")
              for i, (rect, label, col) in enumerate(OVERVIEW)]
for i, (t, pt, label, changed, card) in enumerate(CLICKS_IN):
    nxt = CLICKS_IN[i + 1][0] if i + 1 < len(CLICKS_IN) else END
    SHOTS += [(t - LEAD, 0.6, pt[0] + 100, pt[1], ZOOM), (t + BACK, 0.7, "full")]
    CLICKS.append((t, pt, label))
    if changed:
        LINKS.append((t + 0.9, t + 1.85, (pt[0] + 130, pt[1]), changed, "화면 전환"))
    if card:
        CARDS.append((t + 0.75, min(t + 3.1, nxt - LEAD - 0.2), *card))
for p in POINTS:
    HIGHLIGHTS.append(p if len(p) > 4 else (*p, "accent"))
SHOTS.append((END, 4.0, "full", 1.07))
SHOTS.sort(key=lambda s: s[0])
SUBTITLES = SAY
if HUD_ITEMS:
    HUD = dict(range=(INTRO_END, END - 0.1), title="세션 모니터", items=HUD_ITEMS,
               active=[(0.0, 0)] + HUD_ACTIVE, steps=STEPS)
MUSIC = dict(drop=DROP)
VOICE = dict(provider="edge", voice="ko-KR-SunHiNeural", rate="+5%")
