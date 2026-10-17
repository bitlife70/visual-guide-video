# visual-guide-video

영상을 **코드만으로** 액티브한 해설·하이라이트 영상으로 바꾸는 [Claude Code](https://claude.com/claude-code) 스킬입니다. 영상 유형마다 다르게 처리합니다.

| 프로필 | 대상 | 주요 연출 |
|---|---|---|
| `screen` | 화면녹화·튜토리얼·데모 | 클릭 지점 **줌인**, 스포트라이트, 클릭 **리플**, 화살표 **풍선 도움말**, 영역 하이라이트, 세션 카드, HUD, 진행 칩 |
| `game` | 게임 플레이·보스전 | 멀리 있는 대상 **돋보기 확대**, 피격·치명타 **타격감**(흔들림·플래시·색수차), **슬로모션·빨리감기·정지 화면 해설**, 리액션 **팝업**, HP 게이지 자동 분석 |
| `vlog` | 일상·가족 행사·여행 | 클라이맥스 **슬로모션 + 꽃가루·하트·반짝이 파티클**, 흔들리는 구간 **빨리감기(모션블러)**, 사진 순간 **정지 + 폴라로이드**, 카운트다운 팝업, 사진 콜라주 아웃트로, 따뜻한 색보정 |
| `anim` | 애니메이션 | 귀여운 팝업·스티커, 결정적 장면 정지, 선명한 색보정 |
| `promo` | 광고·홍보·여행 필름 | 원본에 박힌 **글씨 지우기**(같은 장면 프레임으로 복원 + 카메라 이동 보정) → 다국어 **광고 타이포**(히어로·챕터·낙관 도장), **먹물 번짐 전환**, 해·달 **빛 번짐·렌즈 플레어**, 꽃잎·단풍·반딧불 파티클, 시네마 레터박스, 국악풍 **zen** 음악 에너지 곡선 |

공통 기능
- 🎯 움직이는 대상 **추적**(키프레임 보간 + OpenCV 자동 추적 + 템플릿 매칭 + 부모 트랙 따라가기). 말풍선·줌·하이라이트·파티클이 대상을 따라갑니다
- 🎨 색보정 9종(cinematic, warm, danger, mono 등), 구간별 전환
- 🎵 numpy로 합성한 **배경음** 5가지 스타일: pop / epic / chill / cute / zen(가야금·대금·장구·북, 장면별 에너지 arc). 섹션이 자동으로 배치되고 drop 시점을 지정할 수 있으며, 원하는 시각에 스크래치로 끊을 수 있습니다
- 🔊 **원본 소리 유지**(슬로모션·정지 구간 자동 처리) + 효과음 라이브러리(타격·폭발·쇳소리·슬픈 트롬본·심장 박동 등)
- 🎙️ 선택 옵션: **성우 내레이션**(Edge 신경망 TTS / Windows 오프라인 TTS), 슬롯에 맞춘 속도 조절, 자동 덕킹
- 🧩 **커스텀 훅**: 새 효과를 엔진 수정 없이 `timeline.py` 안의 함수로 추가합니다
- 📐 출력 해상도·fps·화질 지정(예: 720p 30fps), 병렬 렌더링, `.srt` 자막 동시 출력

외부 편집 툴·음원·템플릿 없이 Python(OpenCV · Pillow · NumPy · SciPy)과 번들 ffmpeg만 씁니다.

## 설치

```bash
git clone https://github.com/bitlife70/visual-guide-video ~/.claude/skills/visual-guide-video
pip install -r ~/.claude/skills/visual-guide-video/requirements.txt
```

Claude Code에서 다음처럼 요청하면 스킬이 동작합니다.
- "이 화면녹화에 설명 효과랑 배경음 넣어줘"
- "이 게임 영상 재밌게 편집해줘. 보스는 돋보기로 확대하고, 맞을 때마다 코멘트 넣어줘"
- "이 홍보 영상을 영어 광고로 바꿔줘. 원본 한글 글씨는 지우고, 음악은 알아서"

## 직접 사용

```bash
S=~/.claude/skills/visual-guide-video/scripts
python $S/analyze.py video.mp4 --out build/analysis                       # 1) 유형 추정·이벤트·시트·그래프
python $S/analyze.py video.mp4 --out build/analysis --bar player:337,982,626,988   #    (게임) HP 게이지 → 피격·회복·사망 시점
python $S/crops.py video.mp4 --t 7.4 --box 0,760,420,240 --out build/crops.jpg     # 2) 좌표 측정
cp ~/.claude/skills/visual-guide-video/recipes/event_vlog.py timeline.py   # 3) 레시피 복사 후 [1. 채울 값] 작성
python $S/tracks.py timeline.py                                           #    추적 대상 검증 시트
python $S/build.py timeline.py --preview 3.5,7.4,26                       # 4) 미리보기 (원본 시각)
python $S/build.py timeline.py --preview-out 16.6,36.2                    #    미리보기 (출력 시각: 정지·슬로모션)
python $S/build.py timeline.py [--voice edge]                             # 5) 최종 렌더
```

| 옵션 | 설명 |
|---|---|
| `--preview t1,t2,…` / `--preview-out …` | 원본 / 출력 시각을 렌더링해 `build/preview/sheet*.jpg` 생성 |
| `--voice edge\|sapi\|none` | 성우 내레이션. `edge` = 온라인 신경망 음성(문장 텍스트가 Microsoft TTS로 전송됨), `sapi` = Windows 오프라인 음성 |
| `--voice-name` | 예: `ko-KR-InJoonNeural`, `"Microsoft Heami Desktop"` |
| `--audio-only` | 오디오만 생성 |
| `--no-music` | 배경음 없이 |
| `--workers N` | 병렬 렌더링 프로세스 수 |

전체 스키마는 [`templates/timeline_template.py`](templates/timeline_template.py)에 있습니다. 보통은 유형별 레시피에서 시작합니다.
- [`recipes/screen_walkthrough.py`](recipes/screen_walkthrough.py): 화면녹화 튜토리얼. 클릭 목록만 채우면 줌인 → 리플·풍선 → 줌아웃 → 바뀐 곳 화살표 → 요약 카드가 자동으로 이어집니다.
- [`recipes/game_boss_fight.py`](recipes/game_boss_fight.py): 게임 보스전. HP 게이지 분석으로 얻은 피격 시각과 남은 HP를 넣으면 타격감·리액션 팝업·HP 표시·위기 색감·슬로모션·K.O. 연출이 자동으로 들어갑니다.
- [`recipes/promo_film.py`](recipes/promo_film.py): 광고·홍보 필름. 장면 목록(구간·배속·챕터 문구·낙관·파티클·에너지)과 전환 시각을 넣으면 오프닝 카피 → 히어로 타이틀 → 챕터 → 먹물 전환 → 엔드 카드와 음악 곡선이 맞춰집니다.
- [`recipes/event_vlog.py`](recipes/event_vlog.py): 생일·파티 브이로그. 클라이맥스(촛불 끄기)를 넣으면 슬로모션·꽃가루·음악 시작이 맞춰지고, 사진 카운트다운은 정지 + 폴라로이드로, 끝은 사진 콜라주 아웃트로로 처리됩니다.

레시피는 실제 화면녹화(59초), 게임 녹화(2580×1080 93초 → 720p 91초), 휴대폰 영상(50초), 수묵 애니메이션(116초 → 85초 영어 광고)으로 검증했습니다. 영상과 개인 정보는 저장소에 포함하지 않습니다.

## 폰트

맑은 고딕(Windows), Apple SD 고딕(macOS), Noto Sans CJK / 나눔고딕(Linux)과 컬러 이모지 폰트를 자동으로 찾습니다. 찾지 못하면 `VGUIDE_FONT_BOLD`, `VGUIDE_FONT_REGULAR`, `VGUIDE_FONT_EMOJI` 환경변수로 지정하세요.

## License

MIT
