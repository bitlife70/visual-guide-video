---
name: visual-guide-video
description: 영상(mp4)을 분석해 코드로 연출을 입힌 해설·하이라이트 영상을 만든다. 화면녹화(줌인·클릭 리플·풍선 도움말·HUD), 게임 플레이(돋보기 확대·피격 타격감·슬로모션·정지 화면·팝업 텍스트·HP 게이지 분석), 브이로그·애니메이션(대상 추적 말풍선·스티커·색보정·배속)을 영상 유형별 프로필로 처리하고, 신스로 합성한 배경음(pop/epic/chill/cute)·효과음·원본 소리·선택적 성우 내레이션(TTS)을 믹스한다. "화면녹화에 설명 효과 넣어줘", "게임 영상 재밌게 편집", "보스전 하이라이트", "브이로그 자막·효과", "클릭할 때 줌인·풍선도움말", "자막·배경음·성우 입혀줘", "screen recording explainer", "gameplay highlight edit" 등에 사용한다.
---

# Visual Guide Video

영상을 분석해 **타임라인 파일 하나(`timeline.py`)** 를 작성하면, 엔진이 모든 연출·음악·효과음을 코드로 렌더링한다. 외부 편집 툴이나 음원 파일은 쓰지 않는다.

`SKILL_DIR` = 이 SKILL.md 가 있는 폴더. 스크립트는 `python "$SKILL_DIR/scripts/<name>.py"` 로 실행한다.

## 0. 준비

```bash
pip install -r "$SKILL_DIR/requirements.txt"   # opencv-python imageio-ffmpeg numpy scipy pillow edge-tts
```
ffmpeg 는 `imageio-ffmpeg` 번들을 쓴다. 한글·이모지 폰트는 OS 기본을 자동 탐색한다(`VGUIDE_FONT_BOLD/REGULAR/EMOJI` 로 지정 가능).
작업 폴더는 영상 옆에 둔다: `project/timeline.py`, 산출물 `project/build/`, `project/output/`.

## 1. 영상 유형 판별 → 프로필 선택

```bash
python "$SKILL_DIR/scripts/analyze.py" VIDEO --out build/analysis
```
콘솔의 `유형 추정` 과 `build/analysis/sheets/*.jpg` 를 **Read 로 직접 보고** 유형을 정한다. `PROFILE` 하나로 기본값이 바뀌고, timeline.py 에 적은 값이 항상 우선한다.

| PROFILE | 대상 | 기본값 | 핵심 연출 |
|---|---|---|---|
| `screen` | 화면녹화·튜토리얼·데모 | pop 음악, 원본 소리 끔, 진행 바 | SHOTS 줌, CLICKS, LINKS, HIGHLIGHTS, CARDS, HUD, FLOW |
| `game` | 게임 플레이·보스전·하이라이트 | epic 음악(작게), 원본 소리 켬, cinematic 색보정, 30fps | MAGNIFY, IMPACTS, SPEED/FREEZE, POPS, CALLOUTS(@트랙), 게이지 분석 |
| `vlog` | 일상·여행·리뷰 | chill 음악, 원본 소리 켬, warm 색보정 | CALLOUTS, STICKERS, SPEED(배속 이동), 자막, GRADES |
| `anim` | 애니메이션·캐릭터 영상 | cute 음악, vivid 색보정 | POPS(funny), STICKERS, CALLOUTS, FREEZE |

유형마다 **무엇을 설명할지**가 다르다:
- **screen**: "지금 어디를 누르고 무엇이 바뀌는가" → 클릭 지점 줌, 바뀐 패널 화살표, 상태 카드.
- **game**: "무슨 일이 벌어졌나(공격·방어·피격·회복·보스 패턴)" + 재미 → 타격감, 리액션 팝업, 멀리 있는 대상 돋보기, 결정적 순간 정지 해설, 지루한 이동 구간 빨리감기.
- **vlog**: "어디서 무엇을 하는가" + **감정** → 설명보다 분위기. 행사(생일·여행·졸업)의 클라이맥스를 슬로모션·파티클로 키우고, 흔들리는 이동 구간은 빨리감기, 사진 찍는 순간은 정지 + 폴라로이드, 끝은 사진 콜라주 아웃트로.
- **anim**: 캐릭터 리액션 강조 → 귀여운 팝업, 스티커, 결정적 표정 정지.

**공통 편집 원칙 (사용자가 가장 좋아한 부분)**: 불필요한 구간(이동·로딩·카메라가 흔들리는 구간)은 **빨리감기**, 중요한 순간은 **정지(프리즈)** 해서 설명이나 장식을 넣는다. 분석 단계에서 각 구간을 "핵심 / 연결 / 군더더기"로 분류하고 시작한다.

## 2. 분석 — 언제 어디서 무슨 일이

`events.json` 의 이벤트 종류:
- 공통: `cut`(장면 전환), `flash`(번쩍임), `loud`(소리 피크 = 타격음·폭발), `motion`(움직임 피크)
- screen: `switch`(클릭·탭 전환 후보), `big-change`, `scroll`
- 게이지(`--bar`): `bar-drop`/`bar-big-drop`(피격), `bar-low`(위험), `bar-empty`(사망), `bar-rise`(회복)

**게임은 HP 게이지를 반드시 측정**한다. 피격·회복·사망 시점이 프레임 단위로 정확히 나온다.
```bash
python "$SKILL_DIR/scripts/crops.py" VIDEO --t 10,30 --box 200,940,500,100 --step 25 --out build/hp.jpg   # 게이지 좌표 측정
python "$SKILL_DIR/scripts/analyze.py" VIDEO --out build/analysis --bar player:337,982,626,988 --bar boss:1015,911,1590,915
```
- 게이지 박스는 **바 안쪽 한 줄(높이 4~8px)** 로 잡는다. 흰 게이지는 기본 `light`, 색 게이지는 `:any`.
- `bar_<이름>.png`(카이모그래프: 세로=시간)를 Read 로 보고 이벤트가 맞는지 확인한다. 피격 순간 게이지가 붉게 번쩍이거나 연출로 HUD 가 사라지면 오탐이 생기므로, `graph.png` 와 시트로 교차 확인한다.
- 시트는 2초 간격이다. 싸움 구간은 0.3~0.6초 간격으로 프레임을 더 뽑아 **무슨 동작인지(공격/구르기/피격/변신)** 직접 해석한다.

**정확한 좌표**: 반드시 눈금 크롭으로 측정한다.
```bash
python "$SKILL_DIR/scripts/crops.py" VIDEO --t 7.4,13.5 --box 0,760,420,240 --out build/crops.jpg  # 영역, 50px 눈금
python "$SKILL_DIR/scripts/crops.py" VIDEO --t 12 --full --out build/grid.jpg                    # 전체, 100px 격자
```

## 3. timeline.py 작성

**레시피에서 시작한다.** 유형에 맞는 레시피를 timeline.py 로 복사하고 `[1. 채울 값]`(핵심 순간의 시각·좌표·문구)만 채우면 검증된 연출 구조가 자동으로 만들어진다. 그다음 미리보기를 보며 영상에 맞게 항목을 더하거나 고친다.

| 레시피 | 대상 | 채울 값 |
|---|---|---|
| `recipes/screen_walkthrough.py` | 화면녹화 튜토리얼·데모 | 클릭(시각·좌표·문구·바뀐 곳·카드), 강조할 영역, 자막 |
| `recipes/game_boss_fight.py` | 게임 전투 하이라이트 | HP 게이지 위치, 피격(시각·남은 HP), 내 공격, 보스 다운, 회복, 사망/처치, 이동 구간, 해설 자막 |
| `recipes/event_vlog.py` | 생일·기념일·파티 브이로그 | 클라이맥스 시각과 대상, 흔들리는 구간, 사진 카운트다운·정지 프레임, 손님 등장, 마지막 장면 |

레시피의 기본값은 실제 영상으로 검증한 값이라 그대로 두면 예시처럼 동작한다(다른 영상에서는 반드시 다시 측정). 레시피에 없는 항목은 `templates/timeline_template.py` 의 전체 스키마를 참고해 추가한다. 맞는 레시피가 없으면 템플릿에서 시작한다.
작업한 영상의 timeline.py 는 그 영상 폴더에 둔다. **스킬 저장소에는 특정 영상의 타임라인(사람 이름·개인 장면·작업 내용)을 넣지 않는다** — 일반화할 만한 패턴은 레시피와 이 문서로 옮긴다.

**규칙: 시각은 항상 '원본 영상 시각', 좌표는 '원본 픽셀'.** SPEED·FREEZE 로 출력 길이가 바뀌어도 엔진이 알아서 변환한다.
정지 구간 안의 시각은 `(원본 시각, 출력 오프셋초)` 로 쓴다: `(49.45, 1.6)` = 49.45초 정지가 시작되고 1.6초 뒤. 정지 중에 팝업·폴라로이드·아웃트로를 순서대로 띄울 때 쓴다.

### 범용 요소 (모든 프로필)
| 항목 | 용도 |
|---|---|
| `TRIM`, `SPEED`, `FREEZE` | 구간 자르기, 배속·슬로모션(라벨 배지, 라벨 None 이면 배지 없음), 정지 화면(`look` desat=해설용 / photo=셔터 플래시만). 빨리감기는 자동 모션블러(`SPEED_BLEND`) |
| `TRACKS` | 움직이는 대상 키프레임. `auto=True`(OpenCV 추적: 사람·동물) / `auto="match"`(템플릿 매칭: 케이크·간판 등 형태 고정 물체, `until` 까지 키 하나로 추적) / `follow="부모"`(부모 트랙에 붙은 대상, 예: 케이크 위 촛불). 다른 항목에서 `"@이름"`, `"@이름:top"` 으로 가리킨다 |
| `PARTICLES` | 파티클 `confetti/hearts/sparkle/bokeh/notes/stars/snow`. 트랙·좌표에서 `burst`(한 번에 펑) 또는 `rate`(계속), 화면 전체(`at="screen"`) |
| `PHOTOS` | 원본의 한 프레임을 폴라로이드로 띄우기(캡션·각도·떨어지는 등장). 정지 화면·아웃트로 콜라주용 |
| `SHOTS` | 카메라: 좌표 줌 / `"full"` / `"fill"`(레터박스 없이 꽉 채움) / `"@트랙"` 추적 줌 |
| `MAGNIFY` | 돋보기 렌즈: 멀리 있는 대상을 원형으로 확대 + 연결선 + 라벨 |
| `CALLOUTS` | 대상을 가리키는 말풍선(트랙을 따라 움직임) |
| `POPS` | 팝업 텍스트 스타일 `impact/danger/cool/info/funny/small/party/sweet/count`(카운트다운 숫자) |
| `STICKERS` | 이모지 스티커(bob/pulse) |
| `IMPACTS` | 타격감 `hit/heavy/crit/damage/block/parry`: 흔들림+플래시+줌 펀치+색수차(+효과음 자동) |
| `SHAKE`, `FLASH` | 수동 흔들림·번쩍임 |
| `GRADE`, `GRADES` | 색보정 `cinematic/warm/cool/vivid/mono/sepia/danger/dream/night` (구간별 전환) |
| `SFX`, `SFX_VOLUME` | 효과음 라이브러리: hit boom clang pop ding scratch sad_trombone heartbeat shutter slowmo crash whoosh riser party_horn twinkle confetti |
| `SOURCE_AUDIO` | 원본 소리(슬로모션 구간은 피치 하강, 정지 구간은 무음, 빨리감기 구간은 `fast_gain` 만큼 줄임) |
| `MUSIC` | `style` pop/epic/chill/cute, `start`(이 시각부터 음악), `drop`, `end`(+`end_fx` scratch/fade/cut), `volume` |
| `MASTER_GAIN_DB` | 최종 믹스 게인(리미터 전). 휴대폰 영상은 원본이 작아서 +3~5 dB |
| `CUSTOM_LAYERS`, `CUSTOM_FRAME_FX`, `CUSTOM_SFX` | **지시받은 새 효과**를 timeline.py 안 함수로 추가 (아래) |
| `OUTPUT_SIZE`, `FPS`, `QUALITY` | 출력 해상도(예: 720p `(1280, 720)`), fps, CRF |

### 새 효과를 지시받으면 — 커스텀 훅
엔진을 고치지 말고 timeline.py 에 함수를 쓴다. `ctx` 에는 `t`(출력 시각), `ts`(원본 시각), `raw`(원본 프레임), `frame`(현재 캔버스 BGR), `view`, `cv`(오버레이 캔버스), `tl`, `gfx`, `fx`, `W`, `H`, `screen("@boss")`, `window(t0, t1)`(원본 시각 구간 → (alpha, 진행도))가 있다.
```python
def speed_lines(ctx):                           # CUSTOM_LAYERS: 오버레이 그리기 (반환 없음 또는 새 frame)
    w = ctx.window(57.2, 58.4)
    if w:
        x, y = ctx.screen("@boss")
        for k in range(12):
            a = k / 12 * 6.283
            ctx.fx.draw_line(ctx.cv, (x + 300 * math.cos(a), y + 300 * math.sin(a)),
                             (x + 700 * math.cos(a), y + 700 * math.sin(a)), (255, 255, 255), 3, w[0] * 0.6)
CUSTOM_LAYERS = [speed_lines]

def red_pulse(ctx):                             # CUSTOM_FRAME_FX: 프레임 변형 → 새 frame 반환
    return ctx.fx._tint(ctx.frame, (255, 0, 0), 0.15) if ctx.window(76, 78) else None
CUSTOM_FRAME_FX = [red_pulse]

def boss_roar(a):                               # CUSTOM_SFX: a = dict(buf, add, lib, tl, SR)
    a["add"](a["buf"], a["lib"]["boom"](), a["tl"].out(14.4), 0.8)
CUSTOM_SFX = [boss_roar]
```
자주 쓰게 되는 효과는 나중에 `fx.py` 로 옮겨 정식 항목으로 만든다.

### 레이아웃 규칙 (실제로 겪은 문제에서 나온 것)
**공통**
- 이모지는 컬러로 렌더링된다. 단 `▸ ✓ ✕` 같은 기호는 □ 로 깨지므로 이모지(✅ ✖️ 👉 ⏩ ⏸)나 `• → ·` 를 쓴다.
- 자막은 한 줄 40자 안팎. 핵심어는 `[대괄호]` 로 강조. 정지 화면 해설 자막은 `(tf, tf, "...")` 처럼 정지 시각을 시작=끝으로 적으면 정지 동안만 뜬다.
- 같은 순간에 팝업·말풍선·스티커를 3개 이상 겹치지 않는다. 팝업은 0.8~1.2초면 충분하다.

**screen**
- 카드와 하이라이트가 겹치지 않게 시간을 나눈다(카드 → 하이라이트). 카드는 다음 클릭 줌 전에 끝낸다.
- 줌 상태에서 하이라이트가 화면 밖으로 나가면 잘린다 → 배율 1.15~1.3.
- 라벨 배치 `"right"`(화살표), `"above-right"`(표의 행), `"below"`(상단 요소). HUD 는 줌 1.12배 이상에서 미니 모드(좌측 100px).

**game**
- 울트라와이드(21:9)는 16:9 캔버스에 레터박스로 들어간다. 위아래 띠에 배속 배지·자막이 들어가 액션을 가리지 않는다. 꽉 채우려면 `SHOTS` 에 `"fill"`.
- 게이지 하이라이트는 `"above|nodim"` — 화면을 어둡게 하면 액션이 안 보인다.
- 줌은 1.3~1.5배까지만. 액션이 빨라서 과하면 대상이 화면 밖으로 나간다. 확대가 필요하면 `MAGNIFY` 를 쓴다.
- 정지(FREEZE)는 1~2초, 한 영상에 3~4번이면 충분하다. 정지 중에는 CALLOUTS 로 "누가 무엇을" 짚는다.
- 이동·로딩 구간은 SPEED 2~3배로 줄인다. 슬로모션 0.3~0.4배는 피격·결정타 0.5~1초에만.
- 트랙 키프레임은 대상이 크게 움직일 때마다 찍고, 장면이 바뀌는 곳(컷)에서는 같은 값을 두 번(직전·직후) 적어 보간이 튀지 않게 한다. `python "$SKILL_DIR/scripts/tracks.py" timeline.py` 로 시트를 만들어 확인한다.
- HP 이벤트로 피격 시점을 잡고 `IMPACTS` 를 프레임 정확도로 맞춘다. 피격 = `damage`/`crit`, 내 공격 적중 = `hit`/`heavy`.
- 원본 게임 소리를 살리고 BGM 은 작게(volume 0.3~0.45). 사망 시점에 `MUSIC["end"]` + `end_fx="scratch"` 로 음악을 끊고 `sad_trombone` 같은 효과음으로 웃음 포인트를 만든다.

**vlog (가족·행사 영상)**
- 휴대폰 영상은 흔들림이 많다. 흔들리는 이동 구간은 3~4배 빨리감기(모션블러가 자동으로 들어가 부드럽다), 원본 소리는 자동으로 줄어든다.
- 클라이맥스(촛불 끄기·건배·골인)는 0.4배 슬로모션 + 플래시 + confetti burst + party_horn. **음악은 그 순간 시작**(`MUSIC["start"]`) — 그 전엔 원본 소리(생일 노래·대화)를 살린다.
- 사진 찍는 장면은 셔터가 눌린 직후의 **흔들리지 않은 프레임**에서 정지(`look="photo"`)하고 폴라로이드를 띄운다. 정지 프레임은 미리보기로 선명한지 꼭 확인한다(카메라가 움직이는 프레임은 흐릿하다).
- 스티커·팝업·하트를 **얼굴 위에 두지 않는다**. 얼굴 좌표를 측정해 옆이나 위 빈 공간에 둔다. 표정(메롱·윙크)을 가리키려면 스티커 대신 CALLOUTS(`ring=False`)로 옆에서 가리킨다.
- 카운트다운이 화면에 보이면(휴대폰 타이머) `count` 팝업 3·2·1 을 그 시각에 맞추고 pop 효과음을 단다.
- 아웃트로는 정지 화면 위에 폴라로이드 2~3장 콜라주 + 짧은 축하 문구(`OUTRO` 의 `top` 으로 위로 올리고 `stats=[]`).
- 자막·성우 없이도 이야기가 보이게: 인트로 제목 + 장면마다 짧은 팝업 한 줄이면 충분하다.

## 4. 미리보기 반복

```bash
python "$SKILL_DIR/scripts/build.py" timeline.py --preview 3.5,7.4,26        # 원본 시각
python "$SKILL_DIR/scripts/build.py" timeline.py --preview-out 16.6,36.2     # 출력 시각 (정지·슬로모션 중간 확인)
```
`build/preview/sheet*.jpg` 를 **Read 로 보고** 겹침·잘림·가림·좌표 오차·글자 깨짐을 고친다. 라벨 `src ↔ out` 으로 시간 변환도 확인된다. 정지 구간은 원본 시각으로는 확인할 수 없으니 `--preview-out` 을 쓴다.

## 5. 오디오

- **배경음** `MUSIC["style"]`: pop(126BPM 일렉트로 팝), epic(96BPM 타이코·스타카토 현·브라스·합창), chill(82BPM 로파이), cute(132BPM 마림바·피치카토). 모두 intro → A → B → build → drop → outro 구조이며 `drop` 초에 하이라이트가 터진다.
- **원본 소리**: game/vlog/anim 기본 켬. 성우가 말하면 함께 덕킹된다(`SOURCE_AUDIO["duck"]`).
- **레벨 점검**: 게임은 원본 소리가 주인공이다. 구간별 RMS 를 재서 음악이 원본보다 3~5dB 작게, 효과음은 타격 순간에만 들리게 맞춘다.
  ```python
  import tl, music, build; t = tl.load("timeline.py"); m = music.build_music(t)[0] * t.music["volume"]; s = build.source_audio(t, m.shape[1])
  ```
- **성우(선택)** `NARRATION = [(t, "문장")]` (없으면 자막을 읽음). `--voice edge`(Microsoft 신경망, 온라인 — **문장이 Microsoft 로 전송됨을 알린다**) / `--voice sapi`(Windows 오프라인). `build/voice_report.json` 에서 rate 가 +15% 를 넘거나 overflow 면 문장을 줄인다(한국어 ≈ 7음절/초).

## 6. 최종 렌더링과 검증

```bash
python "$SKILL_DIR/scripts/build.py" timeline.py [--voice edge] [--workers 8]
```
프레임을 나눠 여러 프로세스로 병렬 렌더링한 뒤 이어 붙인다(1분 1080p ≈ 2~3분, 8 workers). 백그라운드로 실행한다.

**완료 전 확인 사항**
- 마지막 줄 `[done] ... Ns (expected Ns), N MB` 에서 길이가 일치하는지, 로그에 Traceback 이 없는지 본다.
- 출력에서 프레임 몇 장을 뽑아 확인한다: `ffmpeg -ss T -i out.mp4 -frames:v 1 f.png`
- 음악·효과음은 직접 들을 수 없으므로 구간 RMS 로 확인하고, 사용자에게 직접 들어 보라고 말한다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `scripts/analyze.py` | 메타·유형 추정·장면 전환·소리 피크·게이지 이벤트·그래프·시트 |
| `scripts/crops.py` | 원본 좌표 눈금 크롭 |
| `scripts/tracks.py` | 대상 추적(키프레임 보간·OpenCV), 검증 시트 |
| `scripts/remap.py` | 시간 리매핑(TRIM·SPEED·FREEZE) |
| `scripts/build.py` | 미리보기 / 오디오 믹스(원본 소리 리매핑·리미터) / 병렬 렌더 / SRT |
| `scripts/tl.py` | timeline.py 로더, 프로필 기본값, 좌표·시각 변환 |
| `scripts/render.py` | 카메라(추적·흔들림)·화면녹화 레이어·커스텀 훅 |
| `scripts/fx.py` | 범용 효과: 색보정, 타격감, 돋보기, 말풍선, 팝업, 스티커, 배지 |
| `scripts/gfx.py` | 이징, 리치 텍스트(컬러 이모지), AA 도형, 합성, 폰트 |
| `scripts/music.py` | pop BGM, 효과음 라이브러리, 섹션 배치 |
| `scripts/styles.py` | epic / chill / cute BGM |
| `scripts/voice.py` | TTS(edge/sapi), 슬롯 맞춤 속도, 덕킹 |
| `templates/timeline_template.py` | 전체 스키마 설명이 달린 템플릿 |
| `recipes/` | 유형별 레시피: screen_walkthrough, game_boss_fight, event_vlog |
