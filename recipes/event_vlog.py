"""레시피: 가족 행사 브이로그 (생일·기념일·졸업·파티) — 자막·성우 없이 효과만으로.

사용법: 이 파일을 영상 옆에 timeline.py 로 복사 → [1. 채울 값] 만 채움 → build.py --preview-out 으로 확인 → 미세 조정.
시각은 원본 영상 초, 좌표는 원본 픽셀 (analyze.py 시트와 crops.py 눈금으로 측정).
없는 장면은 None 이나 [] 로 두면 그 연출이 빠진다.

이야기 구조 (이 순서가 가장 반응이 좋았다)
  인트로 제목 → 기다림(노래·대화, 원본 소리만) → 소원/준비(천천히 줌 + 반짝이)
  → ★클라이맥스(0.4배 슬로모션 + 플래시 + 꽃가루 + 이때 음악 시작)
  → 반응(박수·하트) → [흔들리는 이동 = 빨리감기] → 사진 찍기(카운트다운 → 정지 + 폴라로이드)
  → 손님·반려동물 등장 → 마지막 장면 정지 + 폴라로이드 콜라주 아웃트로
"""

# ============================================================ 1. 채울 값
PROFILE = "vlog"
SRC = "recording.mp4"
OUTPUT = "output/event_vlog.mp4"

NAME = "주인공"                         # 제목에 들어갈 이름
TITLE_TEXT = f"[{NAME}]의 생일"         # 예: f"[{NAME}]의 졸업식", "우리 가족 [여름 여행]"
TITLE_SUB = "온 가족이 모인 [특별한 저녁] 💛"
TITLE_TOKENS = [("🎂", "케이크"), ("🕯️", "소원"), ("📸", "사진"), ("🐶", "댕댕이")]
OUTRO_TITLE = f"Happy Birthday, [{NAME}] 💛"
OUTRO_CHIP = "🎉 Happy Day"

# 클라이맥스: 촛불 끄기·건배·축포 등 가장 중요한 순간
CLIMAX_T = 16.75                        # 그 순간 (불이 꺼지는 프레임)
CLIMAX_TEXT = "🎉 생일 축하해! 🎂"
CLIMAX_TEXT_POS = (1230, 280)           # 캔버스 좌표. 주인공 얼굴을 피해 빈 곳에
CLIMAX_FOCUS = (1060, 440)              # 클라이맥스 때 카메라 중심 (얼굴과 촛불이 한 화면에)
# 클라이맥스 대상(케이크 등 모양이 변하지 않는 물체): (처음 보이는 시각, (x, y, w, h)) — 템플릿 매칭으로 따라간다
CLIMAX_OBJECT = (0.5, (1130, 500, 370, 440))
CLIMAX_SPARK_OFFSET = (45, -110)        # 대상 중심 → 반짝이·꽃가루가 나올 지점(촛불) 오프셋

WISH = (13.2, 16.3)                     # 소원 비는/준비하는 구간 (천천히 다가가기 + 반짝이), 없으면 None
WISH_TEXT_POS = (1330, 260)
SINGING = (3.4, 12.9)                   # 노래 부르는 구간 (음표 파티클), 없으면 None
SINGING_POINT = (880, 330)              # 음표가 나올 지점 (노래하는 사람 입 옆, 얼굴에 겹치지 않게)

REACTIONS = [                           # 반응 장면: (t0, t1, (x, y), 이모지) — 박수·하트 + 스티커
    (19.2, 21.3, (600, 380), "👏"),
]
SHAKY = [(21.4, 25.3), (30.45, 34.4)]   # 카메라가 흔들리는 이동 구간 → 3.5배 빨리감기
SLOW_PARTS = [(36.7, 44.9)]             # 덜 중요한 구간 → 2.2배

# 단체 사진: 휴대폰 화면 속 카운트다운 → 찰칵 정지 → 폴라로이드
COUNTDOWN = [28.75, 29.8]               # 화면 속 타이머 숫자가 바뀌는 시각 (마지막이 "1"), 없으면 []
PHOTO_FREEZE_T = 30.15                  # 셔터 직후 '흔들리지 않은' 프레임 (미리보기로 선명한지 확인!)
PHOTO_SOURCE = (28.35, (575, 80, 1300, 600))   # 폴라로이드에 담을 (원본 시각, 영역) — 가장 선명한 화면
PHOTO_CAPTION = "가족 셀카 📸"

GUEST = (34.55, 36.6, (1250, 230), "특별 게스트 등장 🐶")   # (t0, t1, 머리 위 빈 곳, 문구), 없으면 None

FINAL_T = 49.45                         # 마지막 정지 장면 (다 같이 웃는 프레임)
FINAL_RECT = (60, 0, 1860, 1080)        # 폴라로이드로 담을 영역
FINAL_CAPTION = "모두 함께 🐶"
FINAL_CALLOUT = ((470, 552), "메롱~ 😛")  # 마지막 장면의 귀여운 포인트 (좌표, 문구), 없으면 None

# ============================================================ 2. 레시피 (보통 고칠 필요 없음)
OUTPUT_SIZE = (1920, 1080)
QUALITY = 20
FADE_OUT = 1.2
GRADE = "warm"
MASTER_GAIN_DB = 4.0                    # 휴대폰 녹음은 작아서 +4 dB
SOURCE_AUDIO = dict(enabled=True, volume=1.0, fast_gain=0.3)
MUSIC = dict(style="cute", start=CLIMAX_T, volume=0.34)   # 그 전엔 원본(노래·대화)만

TITLE = dict(range=(0.0, 3.2), chip="🎬 FAMILY VLOG", title=TITLE_TEXT, subtitle=TITLE_SUB, tokens=TITLE_TOKENS)
OUTRO = dict(start=(FINAL_T, 1.6), top=120, chip=OUTRO_CHIP, title=OUTRO_TITLE, stats=[],
             footer="사랑하는 사람들과 함께한 하루", footer_y=1000)

SPEED = [(CLIMAX_T - 0.4, CLIMAX_T + 0.4, 0.4)]
SPEED += [(a, b, 3.5, "⏩ x3.5") for a, b in SHAKY]
SPEED += [(a, b, 2.2, "⏩ x2.2") for a, b in SLOW_PARTS]
FREEZE = [(FINAL_T, 6.0, None, dict(look="photo"))]
if PHOTO_FREEZE_T:
    FREEZE.append((PHOTO_FREEZE_T, 2.6, None, dict(look="photo")))

TRACKS = {}
if CLIMAX_OBJECT:
    TRACKS["obj"] = dict(keys=[CLIMAX_OBJECT], auto="match", until=CLIMAX_T + 1.5)
    TRACKS["spark"] = dict(follow="obj", offset=CLIMAX_SPARK_OFFSET, size=(200, 200))
SPARK = "@spark" if CLIMAX_OBJECT else CLIMAX_FOCUS

SHOTS = [(0.0, 0, "full")]
if WISH:
    SHOTS += [(3.2, WISH[0] - 3.2, CLIMAX_FOCUS[0] - 160, CLIMAX_FOCUS[1] + 30, 1.12),   # 기다리는 동안 아주 천천히
              (WISH[0], 1.6, CLIMAX_FOCUS[0] - 80, CLIMAX_FOCUS[1] - 20, 1.3)]
SHOTS += [(CLIMAX_T - 0.55, 0.5, *CLIMAX_FOCUS, 1.38), (CLIMAX_T + 0.6, 0.7, "full")]
if PHOTO_SOURCE:
    (px0, py0, px1, py1) = PHOTO_SOURCE[1]
    t_shot = (COUNTDOWN[0] - 0.4) if COUNTDOWN else PHOTO_FREEZE_T - 1.5
    SHOTS += [(t_shot, 1.0, (px0 + px1) / 2, (py0 + py1) / 2, 1.25), (PHOTO_FREEZE_T + 0.45, 0.3, "full")]
SHOTS += [(FINAL_T - 3.8, 3.8, 900, 470, 1.08)]
SHOTS.sort(key=lambda s: s[0])

PARTICLES = [
    (0.0, CLIMAX_T - 0.15, "sparkle", dict(at=SPARK, rate=7, jitter=90)),
    (3.2, CLIMAX_T - 0.35, "bokeh", dict(rate=1.6, alpha=0.8)),
    (CLIMAX_T, CLIMAX_T + 0.15, "confetti", dict(at=SPARK, burst=110)),
    (CLIMAX_T + 0.25, CLIMAX_T + 4.5, "confetti", dict(rate=26, sfx=False)),
    (FINAL_T - 4.5, FINAL_T, "bokeh", dict(rate=1.4, alpha=0.7)),
    ((FINAL_T, 1.6), (FINAL_T, 6.0), "confetti", dict(rate=22, sfx=False)),   # 아웃트로 제목 위로는 터뜨리지 않는다
]
if SINGING:
    PARTICLES.append((*SINGING, "notes", dict(at=SINGING_POINT, rate=1.6, angle=-50, jitter=30, size=(56, 84))))
if WISH:
    PARTICLES.append((WISH[0] + 0.1, WISH[1], "sparkle", dict(at=CLIMAX_FOCUS, rate=6, jitter=170)))
for a, b, pt, emo in REACTIONS:
    PARTICLES.append((a, b, "hearts", dict(at=pt, rate=5, jitter=60)))
if GUEST:
    PARTICLES.append((GUEST[0], GUEST[1], "hearts", dict(at=GUEST[2], rate=4, jitter=70)))

PHOTOS = [((FINAL_T, 2.2), (FINAL_T, 6.0), FINAL_T, FINAL_RECT, FINAL_CAPTION, dict(pos=(1290, 640), w=640, angle=4))]
if PHOTO_SOURCE:
    PHOTOS += [((PHOTO_FREEZE_T, 0.25), (PHOTO_FREEZE_T, 2.6), *PHOTO_SOURCE, PHOTO_CAPTION,
                dict(pos=(1440, 560), w=560, angle=-6)),
               ((FINAL_T, 1.8), (FINAL_T, 6.0), *PHOTO_SOURCE, "다 같이 찰칵 📸", dict(pos=(640, 640), w=600, angle=-5))]

POPS = [(CLIMAX_T + 0.05, CLIMAX_T + 1.85, dict(x=CLIMAX_TEXT_POS[0], y=CLIMAX_TEXT_POS[1]), CLIMAX_TEXT, "party")]
if WISH:
    POPS.append((WISH[0] + 0.3, WISH[1] - 0.4, dict(x=WISH_TEXT_POS[0], y=WISH_TEXT_POS[1]), "소원 비는 중… 🙏", "sweet"))
if COUNTDOWN:
    POPS.append((COUNTDOWN[0] - 3.3, COUNTDOWN[0] - 1.3, dict(x=960, y=200), "📸 사진 타임!", "sweet"))
    ends = COUNTDOWN[1:] + [PHOTO_FREEZE_T - 0.02]
    POPS += [(t, e - 0.02, "center", str(len(COUNTDOWN) - i), "count") for i, (t, e) in enumerate(zip(COUNTDOWN, ends))]
if PHOTO_FREEZE_T:
    POPS.append(((PHOTO_FREEZE_T, 0.05), (PHOTO_FREEZE_T, 1.2), dict(x=480, y=300), "찰칵! ✨", "party"))
if GUEST:
    POPS.append((GUEST[0], GUEST[1], dict(x=560, y=150), GUEST[3], "sweet"))

STICKERS = [(0.3, CLIMAX_T - 0.15, SPARK, "✨", dict(dy=-150, size=64, motion="pulse"))]
STICKERS += [(a, b, pt, emo, dict(dy=-70, size=88, motion="pulse")) for a, b, pt, emo in REACTIONS]
CALLOUTS = []
if FINAL_CALLOUT:
    CALLOUTS.append(((FINAL_T, 0.1), (FINAL_T, 1.5), FINAL_CALLOUT[0], FINAL_CALLOUT[1],
                     dict(side="left", color="white", size=38, dist=170, ring=False, gap=34)))
FLASH = [(CLIMAX_T + 0.03, (255, 240, 210), 0.35, 0.4)]

SFX = [(CLIMAX_T + 0.02, "party_horn", 0.8), (CLIMAX_T + 0.05, "crash", 0.6), ((FINAL_T, 1.6), "twinkle", 0.6)]
if WISH:
    SFX.append((WISH[0] + 0.2, "twinkle", 0.5))
SFX += [(t, "pop", 0.8) for t in COUNTDOWN]
if PHOTO_FREEZE_T:
    SFX.append(((PHOTO_FREEZE_T, 0.05), "ding", 0.5))
if GUEST:
    SFX.append((GUEST[0], "pop", 0.6))
if FINAL_CALLOUT:
    SFX.append(((FINAL_T, 0.1), "pop", 0.7))
