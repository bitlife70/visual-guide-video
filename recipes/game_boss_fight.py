"""레시피: 게임 보스전 하이라이트 — 공격·방어 해설 + 리액션 + 타격감.

사용법: 이 파일을 영상 옆에 timeline.py 로 복사 → [1. 채울 값] 만 채움 → build.py --preview-out 으로 확인 → 미세 조정.
시각은 원본 영상 초, 좌표는 원본 픽셀.

핵심 순간은 HP 게이지 분석으로 찾는다 (프레임 단위로 정확하다):
  python analyze.py VIDEO --out build/analysis --bar player:x0,y0,x1,y1 --bar boss:x0,y0,x1,y1
    bar-drop / bar-big-drop (player) → HITS_TAKEN 의 시각과 after(남은 HP)
    bar-rise (player) → HEALS,  bar-empty (player) → DEATH,  bar-big-drop (boss) → 보스 다운·처치
  loud 이벤트 중 HP 변화가 없는 것 → 내 공격 적중(HITS_DEALT) 후보. 시트로 동작을 확인한다.

이야기 구조
  인트로 → 이동 구간 빨리감기 → 보스 등장(멀리 있으면 돋보기) → FIGHT!
  → 분석 정지(보스 패턴·내 전략 말풍선) → 공방(맞으면 붉은 타격감·리액션, 때리면 흰 타격감·COMBO)
  → 보스 다운 정지 → 2페이즈 드롭(음악 절정) → 위기(HP 낮음: danger 색감·심장 박동)
  → 결말(처치: 승리 / 사망: 슬로모션 + 정지 + 음악 스크래치 + 슬픈 트롬본) → 전적 카드 아웃트로
"""

# ============================================================ 1. 채울 값
PROFILE = "game"
SRC = "recording.mp4"
OUTPUT = "output/boss_fight_720p.mp4"
OUTPUT_SIZE = (1280, 720)               # 용량을 줄이려면 720p
FPS = 30
QUALITY = 22

GAME = "게임 이름"
BOSS = "보스 이름"
HERO = "주인공"
TITLE_SUB = "[보스전] — 공격·방어 해설판"

HP_BAR = (322, 966, 642, 1002)          # 내 HP 게이지 (하이라이트용 사각형)
BOSS_HP_BAR = (1000, 892, 1605, 928)    # 보스 HP 게이지

TRAVEL = [(3.6, 13.6)]                  # 이동·로딩 구간 → 2.5배 빨리감기
BOSS_APPEAR = 14.45                     # 보스 체력 바가 뜨는 순간
FIGHT_START = 20.6                      # 전투 시작
# 멀리 있는 보스: (t0, t1, 라벨) — 돋보기로 확대. BOSS_KEYS 로 위치를 따라간다
BOSS_FAR = [(15.4, 20.45, f"저 멀리… [{BOSS}] 등장 👀")]
BOSS_KEYS = [(15.2, (1275, 430, 55, 85)), (18.0, (1272, 400, 55, 130)), (20.5, (1210, 250, 160, 280))]

# 분석 정지: (t, 정지 길이, 보스 쪽 (x, y), 보스 설명, 주인공 쪽 (x, y), 전략 설명) — 1~2번이면 충분
ANALYSIS = [(21.62, 1.7, (1300, 360), "🔥 화염 강화 상태", (1290, 760), "🐒 붙어서 때릴 타이밍")]

HITS_TAKEN = [                          # 내가 맞은 순간: (t, 남은 HP 0~1, 화면 중심 (x, y) | None)
    (25.45, 0.85, (1260, 620)), (32.6, 0.66, (1240, 600)), (64.3, 0.78, None),
    (66.1, 0.60, None), (74.9, 0.40, None), (75.5, 0.21, None), (76.15, 0.01, (1280, 700)),
]
HITS_DEALT = [28.95, 29.6, 35.4]        # 내 공격이 크게 들어간 순간
BOSS_DOWN = 37.9                        # 보스가 넘어진 순간 (없으면 None)
PHASE2 = 41.8                           # 2페이즈·패턴 변화 (음악 드롭), 없으면 None
HEALS = [46.4]                          # 회복한 순간
DEATH = 78.2                            # 내가 쓰러진 순간 (이겼으면 None)
VICTORY = None                          # 보스를 처치한 순간 (졌으면 None)
END = 90.5                              # 원본에서 쓸 끝
SKIP_AFTER = [(81.6, 86.3)]             # 결말 뒤 늘어지는 구간 → 1.6배

# 상황 해설 자막 (t0, t1, 문구) — [대괄호]는 강조. 공격/방어/피격/회복을 한 줄씩. 정지 중 해설은 (t, t, "...")
SAY = [
    (3.45, 13.5, "보스방으로 이동 중… 지루하니 [빨리감기] ⏩"),
    (14.4, 20.5, f"체력 바 등장! 오늘의 상대는 [{BOSS}] 👹"),
    (21.62, 21.62, "⏸ 보스의 [강화 상태] — 정면은 위험, 붙어서 딜!"),
    (22.3, 24.85, "[공격] 붙어서 연타! 노란 숫자 = 보스에게 들어간 데미지"),
    (24.95, 26.3, "앗, [반격] 허용"),
    (26.4, 28.2, "[방어] 구르기 회피로 다음 공격은 흘려보내고"),
    (28.3, 30.3, "[반격] 빈틈에 크게 한 방 💥"),
]

# ============================================================ 2. 레시피 (보통 고칠 필요 없음)
TRIM = (0.0, END)
FADE_OUT = 0.8
DAMAGE_REACT = ["아야!", "크억…!", "아야야!", "또 맞음…", "어… 어?", "으악!"]
DEALT_REACT = [("COMBO!", "small"), ("묵직한 한 방!", "impact"), ("나이스!", "cool")]

TITLE = dict(range=(0.0, 3.4), chip="BOSS FIGHT · 하이라이트", title=f"{GAME} [vs] {BOSS}", subtitle=TITLE_SUB,
             tokens=[("🐒", HERO), ("👹", BOSS)])
result = "K.O." if DEATH else "처치!"
OUTRO = dict(start=END - 3.2,
             chip="🎮 오늘의 전적",
             title="[아쉬운 패배] — 다음 판엔 꼭 잡는다!" if DEATH else "[클리어]! 보스 처치 성공 🏆",
             stats=[("⚔️", f"{(DEATH or VICTORY or END) - FIGHT_START:.0f}초 혈투", f"보스 다운 {int(bool(BOSS_DOWN))}회"),
                    ("💔", f"피격 {len(HITS_TAKEN)}회", f"회복 {len(HEALS)}회"),
                    ("💀" if DEATH else "🏆", "결과", result)],
             footer=f"{GAME} · {BOSS} 보스전")
SUBTITLES = SAY

TRACKS = {"boss": dict(keys=BOSS_KEYS)} if BOSS_KEYS else {}

SPEED = [(a, b, 2.5, "⏩ x2.5 · 이동 중") for a, b in TRAVEL]
SPEED += [(a, b, 1.6, "⏩ x1.6") for a, b in SKIP_AFTER]
big = [h for h in HITS_TAKEN if h[1] < 0.7 or h is HITS_TAKEN[0]][:2]  # 첫 피격 + 큰 피격만 슬로모션
SPEED += [(t - 0.5, t + 0.35, 0.35, "🐢 슬로모션") for t, _, _ in big]
if BOSS_DOWN:
    SPEED.append((BOSS_DOWN - 0.6, BOSS_DOWN + 0.2, 0.35, "🐢 슬로모션"))
if DEATH:
    SPEED.append((DEATH - 0.5, DEATH, 0.3, "🐢 슬로모션"))
SPEED.sort(key=lambda s: s[0])

FREEZE = [(t, d, "⏸ 일시정지 · 보스 분석") for t, d, *_ in ANALYSIS]
if BOSS_DOWN:
    FREEZE.append((BOSS_DOWN, 1.1, "⏸ 보스 다운!"))
if DEATH:
    FREEZE.append((DEATH, 1.6, "💀 K.O."))
if VICTORY:
    FREEZE.append((VICTORY, 1.8, "🏆 처치!"))

SHOTS = [(0.0, 0, "full")]
for t, hp, focus in HITS_TAKEN:
    if focus:
        SHOTS += [(t - 0.5, 0.35, *focus, 1.45), (t + 0.9, 0.6, "full")]
for t, d, (bx, by), _, _, _ in ANALYSIS:
    SHOTS += [(t - 0.5, 0.45, bx, by + 90, 1.35), (t + 0.6, 0.6, "full")]
SHOTS.sort(key=lambda s: s[0])

# 치명타(crit: 화면 전체 붉은 플래시)는 아껴 쓴다 — 연달아 쓰면 화면이 통째로 빨개진다
IMPACTS = [(t, "crit" if hp < 0.1 or (i and HITS_TAKEN[i - 1][1] - hp >= 0.3) else "damage")
           for i, (t, hp, _) in enumerate(HITS_TAKEN)]
IMPACTS += [(t, "heavy" if i % 3 == 2 else "hit") for i, t in enumerate(HITS_DEALT)]
if BOSS_DOWN:
    IMPACTS.append((BOSS_DOWN - 0.3, "heavy"))
if PHASE2:
    IMPACTS.append((PHASE2 + 0.3, "heavy"))

low = [t for t, hp, _ in HITS_TAKEN if hp < 0.45]
GRADES = []
if PHASE2:
    GRADES.append((PHASE2 + 0.4, PHASE2 + 4.0, "danger"))
if low:
    GRADES.append((low[0], DEATH or low[-1] + 2, "danger"))
if DEATH:
    GRADES.append((DEATH + 0.1, END - 3.3, "mono"))

MAGNIFY = [(a, b, "@boss", 3.2, label, dict(pos=(1500, 390), r=205)) for a, b, label in BOSS_FAR] if BOSS_KEYS else []

CALLOUTS = []
for t, d, bpt, btxt, hpt, htxt in ANALYSIS:
    CALLOUTS += [(t, t, bpt, btxt, dict(side="right", color="red")), (t, t, hpt, htxt, dict(side="left", color="white"))]

HIGHLIGHTS = [(BOSS_APPEAR, BOSS_APPEAR + 2.5, BOSS_HP_BAR, "👹 보스 체력 게이지", "accent", "above|nodim")]
HIGHLIGHTS += [(t + 0.3, t + 1.6, HP_BAR, f"HP {round(hp * 100)}%" + (" 🚨" if hp < 0.25 else " ⚠️" if hp < 0.65 else ""),
                "accent", "above|nodim") for t, hp, _ in HITS_TAKEN]
HIGHLIGHTS += [(t + 0.2, t + 1.9, HP_BAR, "HP 회복 ✅", "green", "above|nodim") for t in HEALS]

POPS = [(BOSS_APPEAR, BOSS_APPEAR + 1.05, dict(x=960, y=360), "보스 등장!", "danger"),
        (FIGHT_START, FIGHT_START + 0.9, "center", "⚔️ FIGHT!", "impact")]
POPS += [(t, t + 0.9, dict(x=960, y=450), DAMAGE_REACT[i % len(DAMAGE_REACT)], "funny" if i % 3 == 2 else "danger")
         for i, (t, hp, _) in enumerate(HITS_TAKEN)]
POPS += [(t, t + 0.95, dict(x=930, y=400), *DEALT_REACT[i % len(DEALT_REACT)]) for i, t in enumerate(HITS_DEALT)]
if BOSS_DOWN:
    POPS.append((BOSS_DOWN, BOSS_DOWN, "center", "보스 다운! 💥", "impact"))
if DEATH:
    POPS += [(DEATH, DEATH, "center", "K.O. 💀", "danger"), (END - 6.5, END - 4.2, "center", "다음 판엔 꼭… 🙏", "funny")]
if VICTORY:
    POPS.append((VICTORY, VICTORY, "center", "VICTORY 🏆", "impact"))
STICKERS = [(t + 0.05, t + 1.6, (focus or (1260, 600)), "😵", dict(dy=-160)) for t, hp, focus in big if hp < 0.7]

MUSIC = dict(style="epic", drop=PHASE2, end=DEATH, end_fx="scratch", volume=0.32)
SFX_VOLUME = 1.7
SFX = [(BOSS_APPEAR, "boom", 0.6)]
if low:
    SFX += [(low[-1] + 0.3, "heartbeat", 0.9), (low[-1] + 1.0, "heartbeat", 1.0)]
if DEATH:
    SFX.append(((DEATH, 0.55), "sad_trombone", 1.1))
if VICTORY:
    SFX += [(VICTORY, "crash", 0.8), ((VICTORY, 0.3), "twinkle", 0.8)]
