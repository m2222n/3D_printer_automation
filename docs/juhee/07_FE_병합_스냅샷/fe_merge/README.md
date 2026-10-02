# FE 스냅샷 + 라인 MES 와이어프레임 합치기

산출물 = `../20260916_fe_merged.html` (단일 파일, 서버 없이 열린다)

## 다시 만들기
```bash
web-api/scripts/run_demo.sh          # 데모 백엔드 :8085 (다른 터미널)
./docs/juhee/07_FE_병합_스냅샷/fe_merge/make.sh         # 번들 → 스냅샷 → CSS → 합치기 → 검사
```

## 무엇이 무엇인가
| 파일 | 역할 |
|---|---|
| `snapshot.js` | 돌고 있는 FE 를 jsdom 으로 **실제 실행**해 탭 7개의 DOM 을 뜬다 (손으로 옮겨 적지 않는다) |
| `ctl_logic.js` | 와이어프레임 로직 **원본 그대로** (`wireframe_pages.html` 에서 추출) — 기능은 여기서 나온다 |
| `ctl_view.js` | 공정 제어 화면을 **기존 FE 디자인(Tailwind)** 으로 다시 그린다 |
| `line_view.js` | 라인 모니터링(설비·반송 흐름 / 플레이트 파이프라인) |
| `panels.html` | 새 탭 2개의 껍데기 + 확인 모달 |
| `build.js` | 스냅샷 + 새 패널 + CSS → 단일 HTML |
| `check_merged.js` | 합친 결과 검사 14건 (기존 탭 보존 · 새 기능 · 클래스 누락) |

## 규칙
- **기존 7탭은 스냅샷 그대로** — 검사에서 마크업 길이를 원본과 대조한다.
- **로직은 손대지 않는다** — `ctl_logic.js` 를 고칠 일이 생기면 `wireframe_pages.html` 쪽을 고치고 다시 추출한다.
- Tailwind 는 **쓴 클래스만** 만든다 ⇒ 새 마크업에 클래스를 추가하면 `make.sh` 를 다시 돌려야 스타일이 생긴다.
  (검사 ⑬ 이 "CSS 없는 클래스 0개" 를 확인한다)
