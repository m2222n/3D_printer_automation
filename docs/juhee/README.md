# docs/juhee — 라인 MES v2 계획·설계 문서 (2026-09-30 재정리)

> 옛 이름 `docs/plan/` (9/30 이전엔 `.gitignore` 대상이었다 — 그 이전 이력은 git 에 없다).

| 폴더 | 무엇 | 언제 보나 |
| --- | --- | --- |
| `01_조사_실측/` | 코드·DB 전수 조사 결과 (읽기 전용 조사, 코드 변경 0) · `20260921_기존DB스키마_v1_legacy.sql` = 실물에서 뜬 v1 스키마(MariaDB automation + SQLite local.db 한 파일) | "기존에 뭐가 있었나" |
| `02_개발계획/` | 단계 계획서 · 계획 간 대조 · 병존(기존↔신규) 원칙 4편 · **`20261001_10월작업목록.md`**(Notion 10월 작업 목록 ↔ 코드 폴더 대조표, ☑/☐) | "무엇을 어떤 순서로" |
| `03_MES_v2_설계/` | **9/11 설계 정본(9/29 현행화)** — 모듈·스키마·API·대시보드·공정 흐름 · ⭐`서비스_역할_구조.md`(9/30 실측, 세 서비스 역할·DB 소유·의존 방향) + `기존 비교/` | 설계 근거 확인 |
| `04_API_명세/` | API 설계서 → 미결 11건 → **`20260921_API명세.md`(계약 정본, 18개)** | 엔드포인트 계약 |
| `05_작업요청_프롬프트/` | 구조 설계·와이어프레임·제어 화면 요청문(v1~v4·SUP) | 화면이 왜 이렇게 됐나 |
| `06_와이어프레임_HTML/` | 디자인 번들 → `split_wireframe.py` → `wireframe_pages.html` · 제어 화면 조각 · `check_control.js`(43건 검증) | 와이어프레임 재빌드 |
| `07_FE_병합_스냅샷/` | `fe_merge/make.sh` → `20260916_fe_merged.html`(기존 FE + 새 탭) · 9/21 스크린샷 | FE 병합 산출물 |
| `08_작업보고/` | 9/23 BE 작업 보고 | 결과 확인 |

## 재빌드 명령 (리포 루트에서)
```bash
python3 docs/juhee/06_와이어프레임_HTML/build_control_pages.py
python3 docs/juhee/06_와이어프레임_HTML/split_wireframe.py
NODE_PATH=<jsdom> node docs/juhee/06_와이어프레임_HTML/check_control.js
./docs/juhee/07_FE_병합_스냅샷/fe_merge/make.sh     # 데모 백엔드 :8085 선행
```

## 옛 경로 → 새 경로
문서 안 `docs/juhee/<파일>` 참조는 갱신했다. 백틱만 붙은 파일명(`20260922_API개발계획.md` 등)은 그대로이므로 위 표에서 폴더를 찾는다.
`20260911/`·`20260911_MES_v2계획/` = `03_MES_v2_설계/`, `fe_merge/` = `07_FE_병합_스냅샷/fe_merge/`, `병존/` = `02_개발계획/병존/`.
