# `scripts/` — 실행·실증·검증 스크립트

합성데이터 생성(`synth/`)과 모델(`model/`) 사이를 잇는 실행 스크립트 모음. 실물 Depth 촬영, 실측↔합성 변환·정합 검증, 시각화·발표 자료 생성이 여기에 있다.

## 실물 Depth 촬영 (Blaze ToF)

| 파일 | 역할 |
|------|------|
| `blaze_live_view.py` | Blaze ToF 카메라 라이브 뷰 (연결·품질 확인) |
| `blaze_test_capture.py` | 시험 촬영 (밀도·거리·포맷 탐색) |
| `blaze_capture_100.py` | 본촬영 100장 캡처 도구 (그룹·shot 인덱스 관리, 부품 영역 게이팅) |
| `make_capture_plan.py` | 촬영 배치 계획 생성 (부품 그룹 구성) |
| `README_blaze_step0.md` | Blaze 연결·촬영 가이드 |

> 촬영 스펙: 부품↔카메라 약 45~50cm, top-down, 배경 비움. 자세한 촬영 가이드는 `docs/` 참고.

## 실측 → 합성 포맷 변환·검증

| 파일 | 역할 |
|------|------|
| `labelme_to_synthformat.py` | labelme 수동 라벨링(JSON) → 합성 학습 포맷 npz. 배경 0 + 부품 per-scene 0-1 정규화. category_id는 합성과 동일 번호(1~27) |
| `verify_synthformat.py` | 변환 결과 검증 — 배경 처리, 0-1 범위, category_id 분포, **그룹 정답지 대조**(그룹 밖 부품 = 라벨 오류 자동 탐지) |

## sim2real 정합 분석 (도메인 갭)

| 파일 | 역할 |
|------|------|
| `probe_sim2real_matching.py` | 합성↔실측 depth 분포·형상 프로파일 비교 (스케일 갭 진단) |
| `probe_norm_absorb.py` | robust 정규화가 depth 선형 배율을 흡수함을 검증 (재촬영 불필요 근거) |
| `debug_projection.py` | 라벨 polygon → 마스크 투영 디버깅 |

## 시각화·발표 자료

| 파일 | 역할 |
|------|------|
| `viz_norm_absorb.py` / `viz_profile_compare.py` | 정규화 흡수·프로파일 비교 그림 |
| `make_recon_compare.py` / `make_slides_figures.py` | 복원·슬라이드용 figure |
| `render_depth.py` / `render_8views.py` | CAD depth·다각도 렌더 |
| `md_to_html_meeting.py` | 미팅 공유용 Markdown → HTML(PDF 인쇄용) 변환 (표준 라이브러리 자체 파서, 이모지 폰트 치환) |

## Visual Hull 베이스라인 (1주차)

| 파일 | 역할 |
|------|------|
| `run_visual_hull.py` / `run_all_visual_hull.py` | 실루엣 기반 3D 복원 베이스라인 (초기 방향, 현재는 GT·검증 도구로 재배치) |

> ⚠️ 서버 접속 정보(IP·포트·계정)가 포함된 오케스트레이션 스크립트(`auto_chain_*.sh` 등)는 보안상 저장소에 포함하지 않는다(`.gitignore`).
