# 5/20 (수) 사무실 작업 체크리스트

> **사용자 결정 (5/18)**: 길 D (균형 전략) — 트랙 2 데이터 보강 + ACE2 셋업 + 트랙 1 P3/P4 빠른 검증
> **목표**: v2 학습용 데이터 100~150장 추가 + ACE2 라이브 + 트랙 1 큰 부품 ACCEPT 측정

---

## 🛒 출근길 구매 (다이소 또는 편의점)

| 아이템 | 용도 | 예상 비용 |
|--------|-----|---------|
| **회전대 (Lazy Susan)** | yaw sweep 자동화 | 5,000원 |
| **검은 시트 / A4 검정 색지 5장** | 배경 다양화 (검정 흡수재로 일관 배경) | 3,000원 |
| **흰 시트 / A4 흰 색지 5장** | 배경 대비 (검정 vs 흰 + 책상 = 3종 배경) | 2,000원 |
| **A4 인쇄용지 4장** | 향후 A2 합체 (ChArUco 보드 출력용, 5/22 이후) | (사무실에 있을 듯) |
| **클립 / 양면테이프** | 시트 고정 | 1,000원 |

> **체커보드 PDF는 출근 후 사무실 프린터로 출력** (협력사 코드 기준 `(10, 7)` 내부 코너 + 25mm). 5/20 당일 안 써도 5/22 ChArUco 준비용

---

## 🎒 가져갈 자산

### 노트북 / 카메라 / 부품
- [ ] **Mac 노트북 + 충전기**
- [ ] **Basler Blaze + 24V 어댑터 + GigE 케이블** (사무실 보관 중이면 OK)
- [ ] **Basler ACE2 + 12V LOADUS + M8/6P-PWR + RJ45 케이블** (사무실 보관 중)
- [ ] **ipTIME U1G-C 어댑터 (5/15 추가 발주 2번째)** — 5/16~17 도착 예정. **도착 여부 확인**
- [ ] **부품 5종** (회사 출력 부품)
- [ ] **5/15 폰 사진 노트북에 이미 복사 완료** (확인용)

### 측정 도구
- [ ] **캘리퍼스** (P3 56mm 검증용, 새 부품 실측)
- [ ] **줄자 또는 자** (회전대 위치, 거리 측정)

---

## 📋 작업 순서 (오전 → 오후)

### Phase A — 셋업 (~30분, 출근 후 즉시)
- [ ] Mac 부팅 + 사무실 책상 정리 (모니터 / 키보드 옆으로 → valid % > 70% 환경 조성)
- [ ] 카메라 연결: Mac → 어댑터 → GigE → Blaze, Blaze 24V 전원 ON (8초 부팅 대기)
- [ ] `cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation` + `source .venv/binpick/bin/activate`
- [ ] `git pull` (Phase 2 코드 가져오기)
- [ ] `export BASLER_BLAZE_IP=<BLAZE_IP>` (필요 시)
- [ ] `bash scripts/friday_smoke_test.sh` (13/13 PASS 기대)

### Phase B — ACE2 셋업 (~1시간, 어댑터 2개 도착했으면)
- [ ] **ACE2 어댑터 도착 확인** (5/15 추가 발주, 토~월 도착 예정)
  - 미도착 시 Phase B 스킵 → Phase C로
- [ ] 5/8 8단계 절차 재사용 (`reference_basler_blaze_112.md`):
  - 1. 어댑터 Mac 두 번째 USB-C 포트에 연결 → `system_profiler` 5Gb/s 확인
  - 2. ACE2 12V LOADUS + M8/6P-PWR 전원 ON
  - 3. ACE2 RJ45 → 어댑터 → Mac
  - 4. `ifconfig` 으로 ACE2 인터페이스 (en9 or 비슷) 확인 → IP 고정 (Blaze와 다른 사설망)
  - 5. `python bin_picking/tests/test_basler_live.py --discover` 로 ACE2 검색
  - 6. ACE2 라이브 RGB 캡처 1프레임 → valid 확인
  - 7. **Blaze + ACE2 동시 라이브** 시도 (`test_basler_live.py --live --ace2`)
  - 8. 시간/포커스 비교 (협력사 보유 렌즈 사용)
- [ ] **결과 메모**: ACE2 동작 여부 + 시간 + 막힌 단계 → 6000 릴레이

### Phase C — 데이터 보강 촬영 (~2~3시간) ⭐ 핵심

**목표**: 5/15 사진 (단일 환경) → **다양한 환경 100~150장 추가** 학습 robustness ↑

#### C-1. 회전대 활용 자세 다양화 (~1시간)
- [ ] 회전대를 책상 위 놓고 검은 시트 깔기
- [ ] 부품 1개씩 회전대 위 → 폰/Basler ACE2로 yaw 12분할 촬영
- [ ] 5종 × 12 yaw = **60장 목표** (단일 자세, 단일 배경)
- [ ] **part_2 우선** (5/18 학습 약점, Recall 0.656) — 회전대 + 검은 시트 + 자세 2~3개

#### C-2. 배경 다양화 (~1시간)
- [ ] 같은 부품 5종 × 3 배경 = **15장**
  - 배경 1: 회색 책상 (기존)
  - 배경 2: 검은 시트
  - 배경 3: 흰 시트
- [ ] 각 부품 1~2장씩, 큰 변동 X (배경 변수만 분리)

#### C-3. 조명 다양화 (~30분)
- [ ] 천장 형광등 ON (기존) — 5종 5장
- [ ] 창가 자연광 (책상 옮기기) — 5종 5장
- [ ] 스탠드 옆 (직사광 그림자) — 5종 5장
- [ ] = **15장 추가** (조명 변수만 분리)

#### C-4. 부품 겹침 시뮬레이션 (~30분, 핵심)
- [ ] 부품 2~3개를 작은 박스 안에 random 배치
- [ ] 5~10개 시나리오 × Blaze + ACE2 = **10~20장**
- [ ] **실 빈피킹 환경 도메인 갭 완화**

#### C-5. 다양한 각도 (Optional, 시간 남으면)
- [ ] 카메라 위에서 (top-down) — 기존
- [ ] 사선 30~45° — 5종 1장씩
- [ ] = +5장

**Phase C 총 목표**: ~100~115장 (시간 남으면 +5~15)

### Phase D — 트랙 1 빠른 검증 (~30분, 점심 후)
> P5 (작은 부품) 대신 **P3 bracket_sen_1 (56mm 큰 부품)** 으로 ACCEPT 측정

- [ ] P3 회전대 위 단일 자세 배치 (자세 A)
- [ ] `python bin_picking/tests/test_basler_live.py --capture` 1장
- [ ] `python bin_picking/src/labeling/auto_label.py --depth path/to/depth.npy --part bracket_sen_1` 1회만
- [ ] 결과:
  - **ACCEPT 80%+** → 트랙 1 큰 부품 OK → 5/22 다른 큰 부품 (P4) 시도
  - **ACCEPT 50~80%** → 회전대 + 큰 부품으로 시나리오 C (intrinsics 캘리브 필요)
  - **ACCEPT < 50%** → ChArUco 캘리브 분기 (5/22)

### Phase E — 정리 + 동기화 (~30분, 퇴근 전)
- [ ] 촬영 사진 폴더 정리: `~/Desktop/binpicking_yolo_0520/Part_1~5/`
- [ ] (시간 되면) Mac → 6000 scp 미리 백업
- [ ] 6000 릴레이 메시지 보내기 (작업 결과 정리)
- [ ] 카메라/부품/회전대 사무실 보관 (5/22 재사용)

---

## 🎯 Phase별 시간 예산

| Phase | 시간 | 누적 |
|-------|------|------|
| A. 셋업 | 30분 | 30분 |
| B. ACE2 셋업 | 60분 | 90분 |
| C. 데이터 보강 | 150분 | 240분 (= 4h) |
| D. 트랙 1 빠른 검증 | 30분 | 270분 (= 4.5h) |
| E. 정리 | 30분 | 300분 (= 5h) |

**총 ~5시간** (10-15시 또는 11-16시) — 점심 1시간 별도

ACE2 어댑터 미도착 시 → Phase B 스킵 → C에 추가 시간 + 부품 더 다양하게

---

## ⚠️ 주의사항

### 데이터 누수 (data leakage) 방지
- **같은 사진을 여러 번 찍지 X** (Roboflow가 train/valid 분리해도 거의 동일 이미지면 누수)
- 각 사진은 **자세/배경/조명/거리 중 최소 1개 변수** 변화

### 보안 (Roboflow Public plan)
- 부품 사진은 Public 노출 수용 (사용자 결정 5/18)
- 단 **파일명에 회사 부품명 / 모델명 적지 X**
- `KakaoTalk_Photo_*` 같은 자동 이름 유지 권장

### Basler Blaze valid % 확보
- 검정 흡수재 (모니터 / 의자) → valid % 떨어짐
- 깨끗한 책상 + 단순 배경 필수
- 사무실 valid % > 70% 목표 (5/18 4~8%였음)

### part_2 우선 보강
- 5/18 학습 약점 (Recall 0.656)
- 추가 촬영 시 part_2 자세/배경 변수 더 다양하게

---

## 📦 5/20 종료 시점 산출물 목표

- [ ] **사진 100~150장 추가** (Mac `~/Desktop/binpicking_yolo_0520/`)
- [ ] ACE2 동작 여부 확정 (성공 시 RGB 1장 캡처)
- [ ] 트랙 1 P3 ACCEPT 측정 결과 (성공/실패 무관, 데이터 점)
- [ ] 6000 릴레이 메시지 (5/22 v2 학습 입력 자료)

---

## 🔗 관련 문서

- `bin_picking/src/acquisition/basler_capture.py` (Basler API, 5/12 검증)
- `bin_picking/yolo_track/camera/basler_wrapper.py` (5/19 작성)
- `bin_picking/yolo_track/pipeline/bin_picking_main.py` (5/19 작성)
- `scripts/friday_smoke_test.sh` (인프라 검증)
- `docs/binpicking_friday_runbook_20260515.md` (5/15 runbook, 5/20 참고)
- `memory/project_basler_office_setup_0508.md` (어댑터 8단계 검증)
- `memory/project_p5_pilot_blocked_0518.md` (5/22 재시도 조건)
- `memory/project_roboflow_v1_setup_0518.md` (v1 학습 결과 + 약점)
