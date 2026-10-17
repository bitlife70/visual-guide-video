"""비주얼 가이드 타임라인 템플릿.

- 좌표는 모두 '원본 영상 픽셀' 기준 (crops.py 눈금으로 측정). 엔진이 1920x1080 디자인 캔버스로 변환한다.
- 시각은 모두 '원본 영상 시각'(초). SPEED/FREEZE 로 출력 길이가 바뀌어도 엔진이 변환한다.
- 대상(target)은 (x, y) 고정 좌표, (x0, y0, x1, y1) 사각형, 또는 "@트랙[:top|bottom|left|right]".
- 리스트는 비워 두거나 항목째 지워도 된다(SRC 만 필수).
- 텍스트의 [대괄호] 는 강조색, 이모지는 컬러로 렌더링된다.
"""

PROFILE = "screen"                    # screen | game | vlog | anim  (음악 스타일·원본 소리·색보정·fps 기본값)
SRC = "recording.mp4"                 # 이 파일 기준 상대경로
OUTPUT = "output/guide.mp4"
# OUTPUT_SIZE = (1280, 720)           # 기본 1920x1080. 렌더는 1080 디자인 캔버스 → 출력 크기로 축소
# FPS = 30                            # 기본: game/vlog 30, 그 외 원본
# QUALITY = 21                        # x264 CRF (낮을수록 고화질·대용량)
# TRIM = (0.0, 60.0)                  # 원본에서 쓸 구간
# THEME = dict(accent=(255, 138, 61), cyan=(64, 214, 255), green=(80, 224, 140))
# FADE_OUT = 0.55
# CAPTION = dict(size=36, bottom=26)  # 자막 글자 크기, 하단 여백
# PROGRESS = True                     # 하단 진행 바 (screen 기본)

# ---------------------------------------------------------------- 인트로 / 아웃트로 (None 이면 생략)
TITLE = dict(
    range=(0.0, 3.3),
    chip="PRODUCT DEMO",
    title="제품명 [×] 기능",
    subtitle="[한 줄]로 요약한 영상 주제",
    tokens=[("🧠", "역할 1"), ("🛠️", "역할 2")],   # 아이콘 원형 토큰 (선택)
)
OUTRO = dict(
    start=55.0,                       # 이 시각부터 아웃트로 카드 (영상 끝까지)
    chip="🎬 요약",
    title="[핵심 메시지] 한 줄",
    stats=[("⚡", "포인트 1", "설명"), ("📜", "포인트 2", "설명"), ("🚀", "포인트 3", "설명")],
    footer="도구 · 도구 · 도구",
)

# ---------------------------------------------------------------- 시간 연출 (원본 시각 기준)
# SPEED  = [(t0, t1, 배율[, 배지 라벨])]   0.35 = 슬로모션, 2.5 = 빨리감기. 가장자리는 부드럽게 램프. 2배 이상은 자동 모션블러
# FREEZE = [(t, 정지 길이[, 배지 라벨 | None[, dict(look="desat|photo|none", sfx=True)]])]
#          t 에서 화면 정지 (desat: 채도↓ 해설용, photo: 셔터 플래시만). 해설 자막은 (t, t, "...")
# 정지 구간 안의 시각은 (원본 시각, 출력 오프셋초): (49.45, 1.6) = 49.45초 정지 시작 1.6초 뒤 — 모든 항목에서 사용 가능
SPEED = []
FREEZE = []

# ---------------------------------------------------------------- 추적 대상
# 이름: dict(keys=[(t, (x, y, w, h)), ...], auto=False)   키 사이 Catmull-Rom 보간, auto=True 면 OpenCV 추적으로 메움
#        auto="match", until=t  — 템플릿 매칭(형태가 변하지 않는 물체: 케이크·간판), 키 하나로 until 까지 추적
# 이름: dict(follow="부모", offset=(dx, dy), size=(w, h))   부모 트랙에 붙은 대상 (부모 크기 변화에 비례)
# 다른 항목에서 "@이름" (중심) / "@이름:top" (머리 위) 로 가리킨다. 검증: python tracks.py timeline.py
TRACKS = {}

# ---------------------------------------------------------------- 카메라
# (이동 시작 t, 이동 시간, cx, cy, zoom)  — 이동이 끝나면 다음 샷까지 유지
# (t, dur, "full"[, zoom])                 — 전체 화면 (zoom 1.05 정도로 슬로우 푸시 가능)
# (t, dur, "fill")                         — 레터박스 없이 화면을 꽉 채움 (울트라와이드·세로 영상)
# (t, dur, "@트랙", zoom[, (dx, dy)])       — 움직이는 대상을 따라가는 줌
# 클릭: 클릭 0.6~0.9s 전에 클릭점으로 zoom 2.2~2.4 이동, 클릭 0.3s 후 "full" 로 복귀
SHOTS = [
    (0.0, 3.2, "full", 1.06),
    # (6.6, 0.6, 300, 838, 2.3),
    # (7.85, 0.7, "full"),
]

# ---------------------------------------------------------------- 클릭
# (t, (x, y), 풍선 문구)  — t 는 화면이 바뀌기 직전(analyze 이벤트 start - 0.05). 문구 "" 면 리플만.
CLICKS = [
    # (7.55, (198, 838), "🐱 고양이 세션으로 이동"),
]

# ---------------------------------------------------------------- 연결 화살표
# (t0, t1, 출발점(x,y), 목표 사각형(x0,y0,x1,y1), 라벨)  — 클릭한 곳 → 바뀐 탭/패널
LINKS = [
    # (8.45, 9.4, (330, 838), (677, 8, 817, 50), "활성 탭 전환"),
]

# ---------------------------------------------------------------- 하이라이트
# (t0, t1, (x0,y0,x1,y1) | "@트랙", 라벨, 색 "accent"|"cyan"|"green"[, 배치 "right"|"above-right"|"below"|"above"])
# 활성 동안 바깥이 어두워지고 박스가 글로우 펄스. 동시에 여러 개면 합집합 바깥을 어둡게.
# 배치 뒤에 "|nodim" 을 붙이면 어둡게 하지 않는다 (게임 HP 게이지 등): "above|nodim"
HIGHLIGHTS = [
    # (3.9, 6.5, (22, 783, 382, 810), "🧠 코디네이터", "cyan", "right"),
]

# ---------------------------------------------------------------- 화면 고정 카드 (우측 중단)
# (t0, t1, emoji, 제목, [설명 줄, ...][, 배지 텍스트 | None])
CARDS = [
    # (8.3, 10.6, "🐱", "고양이 스컬프터", ["후보 A·B 고양이 3D", "단일 메시 + 헤어 털"]),
]
# CARD_POS = (1884, 560)              # 카드 우상단 기준점 (캔버스 1920x1080)

# ---------------------------------------------------------------- 자막
SUBTITLES = [
    # (3.5, 6.4, "한 화면에서 [에이전트 4개]가 동시에 일합니다"),
]

# ---------------------------------------------------------------- 진행 단계 칩 (선택)
# FLOW = dict(range=(29.0, 33.0), title="📈 진행 상황", area=(440, 1900), y=250,
#             items=[(29.2, "🎨", "단계 1", "부제", "done"), (29.9, "⚡", "단계 2", "부제", "run"), (30.6, "🏆", "단계 3", "부제", "next")])
FLOW = None

# ---------------------------------------------------------------- 좌상단 HUD (선택)
# active: (t, 활성 인덱스 | -1), steps: (t, 단계 라벨). 줌 1.12 이상에서 미니 모드로 접힌다.
# HUD = dict(range=(3.3, 54.4), title="세션 모니터", badge="5 LIVE",
#            items=[("🧠", "코디네이터"), ("🐱", "고양이")],
#            active=[(0.0, 0), (7.6, 1)], steps=[(0.0, "STEP 1 · 전체 구조"), (7.6, "STEP 2 · 세부")])
HUD = None

# ---------------------------------------------------------------- 범용 연출 (게임·브이로그·애니에서 주로 사용)
# 돋보기   (t0, t1, 대상, 배율, 라벨[, dict(pos=(x,y) 캔버스, r=반지름, color="accent")])
MAGNIFY = []
# 말풍선   (t0, t1, 대상, 문구[, dict(side="auto|left|right|up|down", color="white|dark|red|yellow|cyan|green|accent", size=32)])
CALLOUTS = []
# 팝업     (t0, t1, 대상 | "center" | dict(x=, y=) 캔버스, 문구, 스타일 "impact|danger|cool|info|funny|small|party|sweet|count")
POPS = []
# 파티클   (t0, t1, "confetti|hearts|sparkle|bokeh|notes|stars|snow", dict(at="@트랙"|(x,y)|"screen", burst=개수 | rate=초당,
#           angle=-90, jitter=30, size=(min,max), v=(min,max), alpha=1.0, area=(x0,y0,x1,y1) 캔버스, sfx=True))
PARTICLES = []
# 폴라로이드 (t0, t1, 원본 시각, (x0,y0,x1,y1) 원본 영역, 캡션[, dict(pos=(x,y) 캔버스, w=560, angle=-5, enter="drop|pop")])
PHOTOS = []
# 스티커   (t0, t1, 대상, 이모지[, dict(dx=0, dy=-90, size=96, motion="bob|pulse|none")])
STICKERS = []
# 타격감   (t, "hit|heavy|crit|damage|block|parry")  흔들림 + 플래시 + 줌 펀치 + 색수차 + 효과음
IMPACTS = []
# SHAKE = [(t, 세기px, 길이)]   FLASH = [(t, (r,g,b), 세기, 길이)]
# 색보정   GRADE = "cinematic"   GRADES = [(t0, t1, "danger")]  — cinematic warm cool vivid mono sepia danger dream night
# 효과음   SFX = [(t | (t, 출력오프셋), "이름", gain, pan)]  SFX_VOLUME = 1.0
#          hit boom clang pop ding scratch sad_trombone heartbeat shutter slowmo crash whoosh whoosh_down riser click bling
#          party_horn twinkle confetti

# ---------------------------------------------------------------- 커스텀 훅 (지시받은 새 효과는 여기에 함수로)
# def my_layer(ctx): ...      ctx.t ctx.ts ctx.raw ctx.frame ctx.view ctx.cv ctx.tl ctx.gfx ctx.fx ctx.screen("@x") ctx.window(t0, t1)
# CUSTOM_LAYERS = [my_layer]       오버레이 (ctx.cv 에 그림)
# CUSTOM_FRAME_FX = [my_fx]        프레임 변형 (새 frame 반환)
# CUSTOM_SFX = [my_sfx]            효과음: def my_sfx(a): a["add"](a["buf"], a["lib"]["boom"](), a["tl"].out(12.0), 0.8)

# ---------------------------------------------------------------- 성우 내레이션 (선택: --voice edge|sapi)
# (t, 문장[, {"rate": "+10%", "voice": "ko-KR-InJoonNeural"}]). 없으면 SUBTITLES 를 읽는다.
# 한국어 ≈ 7음절/초. 다음 문장 시작 전에 끝나야 함 (build/voice_report.json 확인).
NARRATION = None
VOICE = dict(enabled=False, provider="edge", voice="ko-KR-SunHiNeural", rate="+0%", gain_db=0.0)

# ---------------------------------------------------------------- 배경음 / 원본 소리
# style: pop(126) | epic(96) | chill(82) | cute(132) — 생략 시 프로필 기본. bpm=None 이면 스타일 기본 템포
# start: 음악 시작 시각(그 전엔 원본 소리만). drop: 하이라이트 섹션 시작 시각(초).
# end: 음악을 끝낼 시각, end_fx: "fade" | "scratch" | "cut". volume: BGM 레벨, duck: 내레이션 중 감쇠량
MUSIC = dict(enabled=True, bpm=None, transpose=0, start=None, drop=None, volume=0.82, duck=0.55)
# SOURCE_AUDIO = dict(enabled=True, volume=1.0, duck=0.8, fast_gain=0.3)   # 원본 소리 (screen 기본 끔)
# MASTER_GAIN_DB = 0.0                # 최종 믹스 게인 (휴대폰 영상 +3~5)
