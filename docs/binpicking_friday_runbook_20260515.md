# 5/15 (금) 사무실 운영 Runbook

**대상**: 사무실 도착 직후 ~ 본 캡처 종료까지 한 페이지로 따라할 매뉴얼.
**전제**: 어댑터 도착 ✅ / Mac Blaze 풀 작동 검증 완료 (5/12) ✅ / 5/13~14 재택 사전 디벨롭 완료 ✅
**예상 소요**: 9:00~18:00

## 🎯 5/15 진짜 목표 (5/14 재정의)

**시나리오 E — 단계적 검증**. 데이터 수량보다 **파이프라인 sanity 5가지**:
1. 카메라 intrinsics 정확? (A4 RMS < 2mm)
2. yaw GT 신뢰? (회전대 15° 디스크)
3. 자세 ID GT 신뢰? (ICP top-1 gap)
4. 배경 분리 깨끗? (DBSCAN 회전대 미혼입)
5. **auto_label ACCEPT 비율** ⭐ 점심 시 측정 → Go/NoGo 결정

상세 설계: `memory/project_binpicking_data_collection_design.md`

## 점심 Go/NoGo 분기

| ACCEPT | 다음 액션 | 시나리오 |
|--------|---------|---------|
| > 80% | 오후 풀 sweep 계속 | B (베이직) |
| 50~80% | 체커보드 캘리브 30분 후 재시도 | C (캘리브) |
| < 50% | ChArUco 셋업 1~2시간, 본 수집은 5/18 이월 | D (ChArUco) |

---

## 📋 출근 전 가져갈 것 (목요일 밤 체크)

- [ ] 노트북 (Mac, .venv/binpick 활성화 가능) + 충전기
- [ ] **다이소 회전 받침대** (수동, 5/14 구매) ⭐
- [ ] **한솔 카메라 브라켓 STL** (메일 → 노트북 다운로드) ⭐
- [ ] 캘리퍼스 (있으면 좋음)
- [ ] 핸드폰 (자세 검증 사진용)
- [ ] 부품 5종 + 카메라 + 케이블 + 어댑터 + 도화지/테이프는 사무실 보관 ✅

---

## 🏭 Phase 0 — 공장 직행 (9:00~9:30)

### 0.1 한솔 카메라 브라켓 출력
- [ ] 사무실 들르지 말고 공장 직행 OR 사무실 PC에서 우리 시스템으로 원격 전송
- [ ] STL → Grey V5 (CapableGecko) 전송 → 출력 시작
- [ ] 출력 시간 ~수 시간 → 백그라운드 진행, 수령은 다음 방문 시
- [ ] 한솔 현장 방문 시 (별도 일정) ACE2 케이블/렌즈 인수 + "렌즈 2개" 의미 확인

---

## 🌅 Phase 1 — 셋업 (9:30~10:30)

### 1.1 카메라 마운트
- [ ] Blaze + ace2 통합 마운트 / 또는 Blaze 단독 마운트 (ace2는 공장 보관 중, depth-only 진행)
- [ ] 카메라 광축 책상 위로, 부품 위치 위 **60~80cm**
- [ ] **단단히 고정** (책장 / 모니터 위 / 삼각대 / 책 쌓기). 흔들리면 데이터 무효
- [ ] 24V 어댑터 연결 (LOADUS 아닌 DS240020, 5/8 식별 완료)
- [ ] 이더넷 케이블 연결 (M12 → RJ45, 어댑터 → Mac en8)

### 1.2 네트워크
```bash
cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation
source .venv/binpick/bin/activate
export BASLER_BLAZE_IP=192.168.20.10
```

확인:
```bash
ifconfig en8 | grep "inet "
# 기대: inet 192.168.20.1 netmask 0xffffff00 (Wi-Fi와 분리)
ping -c 2 192.168.20.10
# 기대: 1.6~2.7ms (Wi-Fi 충돌 시 11~76ms)
```

### 1.3 카메라 인식
```bash
python bin_picking/tests/test_basler_live.py --discover
# 기대: Blaze1 (S/N 40737830) 발견. ace2는 --no-ace2 로 제외 진행
```

❌ 발견 안 되면:
- 어댑터 깜빡 LED 확인 (en8 link up?)
- Blaze 후면 STATUS LED 녹색 깜빡 + ETHERNET 빨강?
- `BASLER_BLAZE_IP` export 됐는지 (`echo $BASLER_BLAZE_IP`)

---

## 🌅 Phase 2 — 인프라 sanity check (9:30~11:30)

### 2.1 라이브 뷰어 시야 확인 (5분)
```bash
python bin_picking/tests/live_viewer_basler.py
```

확인:
- [ ] FPS 18~22 (정상 20.1)
- [ ] valid % > 70% (책상 위 평평한 영역)
- [ ] depth median 600~900mm (60~80cm 거리)
- [ ] JET 컬러맵 정상 (흰=가까움, 빨강=멈)

키:
- `s`: 스냅샷 저장
- `c`: 컬러맵 토글
- `r`: 자동 범위 (어두우면)
- `+/-`: 범위 수동 조절
- `ESC` / `q`: 종료

### 2.2 A4 평면 intrinsics sanity check (10분) ⭐
**왜 중요**: intrinsics 추정값 (fx=553) 검증 안 하면 모든 라벨 RMSE 가 체계적 부풀어남.

준비:
- [ ] A4 흰 종이 한 장 책상에 평평하게 (구김 없이)
- [ ] 카메라 정면 60~80cm, 종이 중심이 시야 중심

실행:
```bash
python bin_picking/tests/check_intrinsics_planar.py --capture-and-check \
    --output /tmp/planar_check_$(date +%H%M)
```

**판정**:
| RMS | 상태 | 행동 |
|---|---|---|
| < 2.0mm | ✅ PASS | 본 캡처 진행 |
| 2.0~5.0mm | ⚠️ WARN | `auto_label.py --max-rmse-mm 3.0` 게이트 완화로 진행, RMSE 분포 모니터링 |
| > 5.0mm | ❌ FAIL | ChArUco 정식 캘리브 필요. 본 캡처 보류 |

### 2.3 카메라 흔들림 검증 (5분) — 회전대 미사용 시
```bash
# 부품 없이 책상 평면만 5장
for i in 1 2 3 4 5; do
  python bin_picking/tests/test_basler_live.py --live --save --no-ace2 \
    --output /tmp/shake_test/frame_$i
  sleep 1
done
```
- [ ] 5장 depth median 표준편차 < 0.5mm (정상)
- 어긋나면 카메라 마운트 재점검 (책장 진동, 삼각대 헐거움)

### 2.3.5 회전대 셋업 (10분) ⭐ 5/14 신규
**왜 중요**: yaw GT 신뢰도. 손으로 던지면 silent bias (1pager § 8 #17)

준비:
- [ ] 다이소 회전 받침대 카메라 앞 60~80cm 거리
- [ ] 15° 분할 종이 디스크 (도화지 + 사무실 인쇄) 회전대 위에 부착 — 24분할 마커
- [ ] 회전대 위 **검은 배경 시트** (사무실 도화지 검은색 활용 — 약점 #4: DBSCAN 회전대 미혼입)
- [ ] 회전대 0° 위치 = 카메라 방향 기준점 표시

확인:
- [ ] 라이브 뷰어로 회전대 영역만 시야 중앙
- [ ] valid % 70%+
- [ ] 부품 없이 빈 회전대 캡처 1장 → DBSCAN으로 클러스터 안 잡히는지 확인 (Phase 3 디버깅용 baseline)

### 2.4 부품 자세 던지기 검증 (40분) ⭐⭐⭐
**핵심 작업**: yaml null 채우기. 빠뜨리면 라벨 신뢰도 본질적 손상.

매뉴얼: [docs/binpicking_pose_validation_protocol.md](binpicking_pose_validation_protocol.md)

부품별 7~8분 × 5종 = ~35분. 우선순위:
1. **P5 main_body** (대칭 의심 1순위)
2. ⑤ plate_e (첫 캡처 대상)
3. P3 bracket_sen_1 (4/22 매칭 실패 부품)
4. P2 cam_f_bracket
5. P1 guide_paper_cover

각 부품마다:
- [ ] 책상 위 10cm 위에서 10회 자유낙하 → 자세별 멈춤 횟수 기록
- [ ] 핸드폰 사진 (자세별 위 + 옆 = 2장)
- [ ] `bin_picking/config/stable_poses.yaml` 직접 편집:
  - 부품 레벨 `human_label` (외관 한 문장)
  - 부품 레벨 `symmetry_groups` (대칭 있으면 `[["A","B"]]`, 없으면 명시적 빈 리스트 또는 null 유지)
  - 자세별 `human_label` (외관)
  - 자세별 `pickable` (true/false/null)
  - 자세별 `regrasp_to` (대상 자세 id 또는 null)

⏰ 시간 부족 시 우선순위 1~3만 완료, 4~5는 본 캡처 차차 진행하며 갱신

### 2.5 핸드폰 사진 워크플로우 (Phase 2.4 동안)

부품 5종 × 자세 N × 2장 (위 + 옆) = **20~30장 이상 예상**. 체계적으로 관리 안 하면 어느 사진이 어느 부품 어느 자세인지 5/18 월요일 되면 헷갈림.

**촬영 명명 규칙** (사진 찍기 직전 핸드폰 파일명 메모 또는 폴더 분류):
```
P5_main_body_poseA_top.jpg     ← 위에서 본 컷
P5_main_body_poseA_side.jpg    ← 옆에서 본 컷
P5_main_body_poseB_top.jpg
...
```

**촬영 팁**:
- 부품 옆에 자세 id 적은 종이 함께 찍기 (사진만 봐도 id 식별 가능)
- 또는 자세 id 손가락으로 가리키며 촬영
- 배경 일관 (책상 위 흰 종이) — 5/18 본 캡처 배경과 일치하면 더 좋음
- 핸드폰 가로 모드 (yaml 검토 시 비교 편함)

**Mac 으로 옮기는 절차** (Phase 2 종료 직전, ~10분):
1. AirDrop / iCloud / USB 케이블 — 가장 익숙한 방식
2. Mac 의 `~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/bin_picking/models/pose_validation_photos_20260515/` 폴더에 저장
3. **이 폴더는 .gitignore 됨** (`bin_picking/models/captures/` 외 추가 필요시 .gitignore 갱신)

**참고용 보관**:
- 5/18 이후 부품 자세 식별 모호 시 다시 봄
- yaml 의 `human_label` 작성 시 사진 보면서 묘사
- 추후 새 부품 추가 시 동일 형식으로 확장

⚠️ **사진을 git 에 commit 하지 말 것** — 회사 부품 사진은 보안 영역. 외부 유출 가능 출력물 (`CLAUDE.md § 보안 원칙`).

---

## 🌞 Phase 3 — P5 시범 캡처 (11:30~12:00)

### 3.1 카메라 시야 + 부품 배치
- [ ] 라이브 뷰어로 P5 main_body 배치
- [ ] 부품이 시야 중앙, 60~80cm 거리, valid % 70%+
- [ ] 자세 A (윙 위로) 로 놓음

### 3.2 시범 5장 캡처
```bash
mkdir -p /tmp/p5_trial
for i in 1 2 3 4 5; do
  python bin_picking/tests/test_basler_live.py --live --save --no-ace2 \
    --output /tmp/p5_trial/frame_$i
  read -p "다음 yaw로 살짝 회전 후 Enter: "
done
```

### 3.3 auto_label 첫 실 데이터
```bash
python bin_picking/src/labeling/auto_label.py \
    --capture-dir /tmp/p5_trial/ \
    --part main_body \
    --camera blaze-112 \
    --output bin_picking/models/dataset_v1/
```

판정:
| ACCEPT % | 행동 |
|---|---|
| **≥ 80%** | ✅ 본 캡처 진입 (Phase 4) |
| 50~80% | ⚠️ REVIEW 사유 확인 후 결정 (SOP § 5.1) |
| < 50% | ❌ 셋업 디버깅 (거리/CAD/intrinsics) — 점심 후 재시도 |

---

## 🍴 점심 — Go/NoGo 결정 ⭐ (12:00~13:00)

오전 sanity 5가지 체크:
- [ ] 1. intrinsics 정확? (A4 RMS < 2mm)
- [ ] 2. yaw GT 신뢰? (회전대 15° 디스크 정렬 OK)
- [ ] 3. 자세 ID GT 신뢰? (자세 던지기 검증 5종 완료 + ICP top-1 gap 측정)
- [ ] 4. 배경 분리 깨끗? (DBSCAN에 회전대 미혼입)
- [ ] 5. **ACCEPT 비율** ⭐

**시나리오 분기 (시나리오 E)**:

| ACCEPT | 시나리오 | 오후 행동 |
|--------|---------|---------|
| ≥ 80% | **B 통과** | 풀 sweep (Phase 4 진행) |
| 50~80% | **C 추가** | 체커보드 캘리브 30분 → INTRINSICS_VERSION 2.0 → P5 재캡처 |
| < 50% | **D 강제** | ChArUco 셋업 1~2시간 → 본 수집 5/18 이월. 오후는 ChArUco 인프라 구축 |

**ChArUco 결정 시 작업** (시나리오 D):
- A4 ChArUco 보드 사무실 인쇄 (cv2.aruco.CharucoBoard)
- `charuco_pose.py` 신규 작성 (~150줄)
- `calibrate_intrinsics.py` 신규 작성 (~100줄)
- `capture_session.py --charuco` 모드 추가
- 본 수집은 5/18~로 이월

상세: `memory/project_binpicking_data_collection_design.md` § 시나리오 비교

---

## 🌞 Phase 4 — P5 본 캡처 (13:00~17:00)

### 4.1 P5 자세 A 풀 yaw sweep
```bash
python bin_picking/tests/capture_session.py \
    --part main_body --pose A --light normal --bg white \
    --yaw-step 30
# yaw 12장 (30° 간격, 차원 축소 옵션)
# 또는 --yaw-step 15 로 24장 (풀)
```

세션 흐름:
- 각 yaw마다 회전대 돌리고 Enter
- `s` 로 스킵 / `q` 로 종료
- 종료 후 capture_session.json 자동 저장

### 4.2 자동 라벨링
```bash
python bin_picking/src/labeling/auto_label.py \
    --capture-dir bin_picking/models/captures/20260515_main_body_poseA_normal_white \
    --part main_body \
    --camera blaze-112 \
    --output bin_picking/models/dataset_v1/
```

확인 (`print_summary` 출력):
- [ ] ACCEPT 비율 ≥ 80%
- [ ] RMSE median < 1.5mm
- [ ] pose_match_score median > 0.95
- [ ] 자세 분포: 모두 pose_A (단일 자세 캡처라)

### 4.3 P5 자세 B/C 진행 (시간 남으면)
- 자세 던지기 검증 결과대로 자세 A·B 대칭이면 통합, 아니면 별도
- ACCEPT 미달이면 자세 폐기 또는 게이트 완화

### 4.4 조명/배경 변형 (시간 남으면)
- SOP v1.1 § 1.3: 변형 전 라이브 뷰어로 valid % 70%+ 확인
- side 조명은 그림자 위험 → valid % FAIL 시 스킵

---

## 🌇 Phase 5 — 결과 분석 + 정리 (17:00~19:00)

### 5.1 데이터셋 v1 검증
```bash
find bin_picking/models/dataset_v1/main_body -type d
# 기대: pose_A/{accept,review,fail} 구조
ls bin_picking/models/dataset_v1/main_body/pose_A/accept/*.json | wc -l
# 기대: ACCEPT 프레임 수
```

### 5.2 REVIEW 큐 분석 (SOP v1.1 § 5.1)
```bash
cat bin_picking/models/dataset_v1/run_summary_*.json | jq '.results[] | select(.auto_status == "REVIEW") | .review_reason' | sort | uniq -c
# 사유 분포 확인 — rmse_high 다수면 intrinsics 의심
```

### 5.3 ACCEPT 자세 분포 vs yaml probability 비교
- yaml `main_body.stable_poses[].probability` 와 ACCEPT 자세 분포 ±20% 이내인가?
- 어긋나면 yaml 재검토 또는 캡처 편향

### 5.4 카메라 사무실 보관
- [ ] 카메라 전원 OFF
- [ ] 어댑터 / 케이블 정리
- [ ] 5/18 (월) 다시 셋업 위해 위치 기록 (사진)

### 5.5 메모리 갱신
- [ ] `CLAUDE.local.md` § W19 5/15 진행 기록
- [ ] `MEMORY.md` P0 갱신
- [ ] `project_week_plan_0511.md` 5/15 실측 결과 + 5/18~ 다음주 계획

### 5.6 dual push
```bash
git add -A
git commit -m "feat(binpicking): 5/15 본 캡처 — P5 main_body 자세 A 데이터셋 v1 첫 진입"
git push origin main && git push personal main
```

---

## 🚨 트러블슈팅 빠른 참조

| 증상 | 1차 대응 | 상세 |
|---|---|---|
| `--discover` 0개 | `echo $BASLER_BLAZE_IP` 확인 → export 재실행 | [SOP § 5](binpicking_capture_sop_20260511.md) |
| valid % < 70% | 거리 조정 (60~80cm) / 조명 추가 / SLA 광택은 무광 페인트 | SOP § 5 |
| A4 평면 RMS > 5mm | ChArUco 캘리브 또는 본 캡처 보류 | check_intrinsics_planar.py 출력 |
| ACCEPT < 50% | (a) 셋업 점검 (b) `--part main_body` 강제 (c) CAD 캐시 재빌드 | SOP § 5.1 |
| pose_id 자세별 불일치 | yaml `human_label` 비교, `symmetry_groups` 누락 의심 | pose_validation_protocol.md |
| 한 yaw 에서 cluster 0개 | 부품 시야 밖 / ROI 확장 | SOP § 5 |
| 시간 부족 | 차원 축소 (yaw 12장 + 조명 normal 만 + 배경 white 만) | 1pager § 5.2 |

---

## 📞 비상 연락

- 한솔 김주엽 과장 — Basler ace2 부품 (depth-only 진행이라 5/15 X)
- 예승님 — 5/19~ 방문 일정 (5/15 X)
- 대표님 — 출장 중, 복귀 시 1pager v2.4 align

---

## 🎯 5/15 종료 시 ✅ 체크

- [ ] A4 평면 sanity PASS (RMS < 2mm)
- [ ] 부품 5종 자세 던지기 검증 (yaml null 채움)
- [ ] P5 main_body 자세 A 풀 데이터셋 (~12~24장)
- [ ] ACCEPT 비율 ≥ 80% 확인
- [ ] dataset_v1/main_body/pose_A/ 폴더 구조 OK
- [ ] 카메라 사무실 보관 + 위치 사진
- [ ] dual push 완료
- [ ] 5/18 (월) 계획 (P5 자세 B/C + P3 또는 P5 풀)

→ 위 8개 모두 ✅면 6/2 부트캠프 마감 일정 정상 궤도.

---

## 📚 관련 문서

- 학습 데이터 전략 1pager v2.4: [binpicking_learning_data_strategy_1pager_20260511.md](binpicking_learning_data_strategy_1pager_20260511.md)
- 데이터 수집 SOP v1.1: [binpicking_capture_sop_20260511.md](binpicking_capture_sop_20260511.md)
- 부품 자세 검증 매뉴얼: [binpicking_pose_validation_protocol.md](binpicking_pose_validation_protocol.md)
