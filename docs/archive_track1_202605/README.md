# ⛔ 아카이브 — 빈피킹 트랙1 / YOLO 트랙2 시기 문서 (2026-04~05)

> **여기 있는 문서는 전부 폐기됐다. 실행에 쓰지 말 것.**
> 지우지 않고 남긴 이유 = `CLAUDE.md`가 당시 판단 근거로 인용하고 있고,
> **"왜 그때 그렇게 정했는지"**가 지금 결정을 되짚을 때 필요하기 때문이다.
> (2026-08-19 `docs/`에서 이 폴더로 이동)

## 무엇이 이 문서들을 대체했나

| 시기 | 접근 | 상태 |
|---|---|---|
| ~5/18 | **트랙1** = Open3D 6DoF (FPFH + RANSAC + ICP) | 🔴 P5 정체로 보류 |
| 5/18~5/27 | **트랙2** = RGB YOLO (Roboflow + YOLOv8/v11) | 🔴 depth_track으로 전환 |
| **현행** | **depth_track** = depth-only + CAD codebook | ✅ `bin_picking/depth_track/` |

⭐ 현행 인식은 **RGB를 쓰지 않고 depth만** 본다. 그래서 여기 있는 RGB 촬영 가이드·
조명 지침·YOLO 라벨 규칙은 **지금 파이프라인과 맞지 않는다.**

## 현행 문서는 어디에

| 용도 | 현행 |
|---|---|
| 촬영 현장 카드 | `bin_picking/FIELD_CARD_0818.md` |
| 라벨링 | `bin_picking/LABEL_CARD_0819.md` |
| 배경재 판정 | `bin_picking/tests/check_background_material.py` |
| 전체 현황 | `CLAUDE.md` + `CLAUDE.local.md` |

## 파일 목록

| 파일 | 내용 | 폐기 사유 |
|---|---|---|
| `binpicking_learning_data_strategy_1pager_20260511.md` | 학습 데이터 전략 1pager v2.5 (경영진 align용) | 트랙1 전제. 리스크 목록 일부는 여전히 참고 가치 |
| `binpicking_capture_sop_20260511.md` | 데이터 수집 SOP | 트랙1 촬영 규격(RGB+depth 동시) |
| `binpicking_pose_validation_protocol.md` | 부품 안정자세 검증 프로토콜 | ⭐ **"부품은 빈에 눕는다"는 전제**는 살아남아 8/6 그리퍼 판정의 근거가 됐다 |
| `binpicking_friday_runbook_20260515.md` | 5/15 사무실 운영 런북 | 일회성 |
| `factory_capture_20260520.md` | 5/20 공장 촬영 가이드 | YOLO 트랙2 |
| `office_checklist_20260520.md` | 5/20 사무실 체크리스트 | 일회성 |
| `binpicking_report_0417.md` | 4/17 진행 보고 | 시점 현황 |
