# 빈피킹 학습 데이터 전략 — 1pager (대표님 align용)

**작성**: 2026-05-11 (정태민)
**버전**: v2 (5/11 코드 작업 + 5종 자세 실측 반영)
**목적**: 대표님 5/6 지시 이행을 위한 학습 데이터 전략 + 셀프 판단 영역 align

**v1 → v2 변경사항**:
- § 2 부품 5종 자세 추정 → 실측치 업데이트 (② 추정 틀림, ① 대칭 발견)
- § 5 목표 데이터셋 자세 수 정정 (③ 4 → 5자세 등)
- § 8 리스크에 BLAZE intrinsics 캘리브 항목 추가
- § 10 의사결정 기록에 5/11 후반 (코드 작업, ace2 모델명 정정 등) 추가
- 신규 § 11 산출물 인벤토리 (코드 5종 + 문서 3종)

**v2.1 → v2.2 변경사항 (5/11 오후, 어댑터 도착 후 검증 중 추가 보강)**:
- § 6 실험 계획: 5/15 → 5/11 단축 반영 (어댑터 조기 도착)
- § 8 리스크: ACE2 렌즈 초점거리 미확정 항목 추가 (한솔 보유, 8/12/16mm 분기)
- § 10 의사결정 기록: 5/11 오후 (어댑터 도착, 검증 Step 1~3 PASS, sudo 정정, 양식 합의)
- § 12 신규: Mac ↔ 6000 환경 분담 (5/11 명확화)
- 운영 주의 (신규 sub-section): Basler GigE = sudo 불필요 (RealSense D435 USB 패턴 적용 금지)

**v2.2 → v2.3 변경사항 (5/12, Mac Blaze 풀 작동 검증 완료)**:
- § 2 BLAZE 사양 정정: width 640→**848 (실측)**, fx 417→**553** (재계산), cx 320→**424** (width/2)
- § 8 리스크 #15 신규: macOS Blaze Supplementary 미지원 → ✅ 해소 (pypylon 단독으로 풀 작동 확인)
- § 8 리스크 #16 신규: EnumerateDevices 미동작 → IP 직접 fallback 워크어라운드
- § 10 의사결정 5/12 추가: Blaze 풀 작동 / 192.168.20/24 영구 분리 / Push 정책 명확화 (모든 commit dual)
- § 12 환경 분담: IPC-510 우선순위 ↓ (Mac 단독 데이터 수집 진입 가능 확정)
- § 13 신규: Mac Basler 운영 환경 (BASLER_BLAZE_IP 환경변수 / 192.168.20.x / dual push 정책)

**v2.3 → v2.4 변경사항 (5/14 재택, 학습 데이터 라벨 신뢰도 인프라 + 6/2 부트캠프 마감)**:
- 🎯 **§ 0 신규: 6/2 KAIST 3단계 부트캠프 회사 데이터 프로젝트 마감 도입** — 사무실 가용 4~5일 (5/15·5/18·5/22·5/25·5/29·6/1), 5종 ~1,200~2,400장 목표, 주제 결정 W21 (5/25~)
- § 5 목표 데이터셋 — 차원 축소 옵션 추가 (yaw 24→12 / 조명 3→2 / 배경 3→2 = 1종 380→~200장, 5종 ~1,200장)
- § 6 실험 계획 — 5/15 일정 재조정 (P5 자세 A만 풀, B/C는 시간 남으면). 5/18~6/1 본격 수집 일정 명시
- § 8 리스크 #8 갱신 — intrinsics 캘리브 = `check_intrinsics_planar.py` 로 5/15 즉시 검증 가능 (RMS < 2mm 임계)
- § 8 리스크 #17 신규 — **데이터셋 silent bias** (auto_label REVIEW 큐 무시 시 어려운 자세 underrepresented). SOP v1.1 § 5.1 대응
- § 8 리스크 #18 신규 — **단독 부품 도메인 갭** (학습 데이터 = single-instance / 실 빈피킹 = cluttered + occlusion). 6월 합성 데이터 보강 검토
- § 10 의사결정 5/13~5/14 추가 (스키마 확장 / 대칭 그룹 / 검증 매뉴얼 / SOP 보강 / intrinsics sanity / capture wrapper)
- § 11 산출물 인벤토리 갱신 (코드 6→9: + check_intrinsics_planar + capture_session + auto_label intrinsics_version / 문서 3→4: + pose_validation_protocol)
- § 14 신규: 학습 데이터 라벨 신뢰도 체크리스트 (5/15 본 캡처 직전 자가 점검)

---

## 🎯 0. 6/2 마감 — KAIST 3단계 부트캠프 회사 데이터 프로젝트

| 항목 | 값 |
|---|---|
| 시작일 | **2026-06-02 (화)** |
| 프로젝트 기간 | 6주 (~7/9) |
| 입력 자료 | 빈피킹 5종 데이터셋 v1 (1,200~2,400장) + 라벨 (`auto_label.py` 출력) + CAD + stable_poses.yaml (사람 검증 완료) + 본 1pager |
| 주제 결정 시점 | W21 (5/25~5/29) — 데이터 모인 후 함께 결정 |

**준비 기간 21일 (5/13~6/1) 중 사무실 가용 = 4~5일**:
- 5/15 (금) — P5 시범 + 자세 검증 + 자세 A 풀 캡처
- 5/18 (월) — 본격 수집 1일차
- 5/22 (금) — 본격 수집 2일차 (예승님 방문 일정 겹치면 E2E 우선)
- 5/25 (월) — 본격 수집 3일차 + 부트캠프 주제 결정
- 5/29 (금) — 본격 수집 4일차 + 미니 학습 sanity check 검토
- 6/1 (월) — 부족분 보충 + 데이터셋 v1 최종 검증

**리스크**: 첫 캡처 (5/15) ACCEPT 80% 미달 시 디버깅으로 1~2일 손실. 차원 축소 (1,200장 목표) 가 안전.

---

## 1. 배경

**대표님 5/6 지시 4가지** (`memory/project_binpicking_ceo_directive_0506.md`):
1. Basler 카메라 로컬 테스트 — 로봇 장착 추후, 인식 검증 먼저
2. 공장 실물 부품 다각도 촬영 + 학습 ⭐
3. **X/Y 각도 (뒤집기) 데이터 고민** ⭐ — 코드 짜기 전 명세 → align
4. 예승님 연락 — 좌표 명세 + 바텀비전 자료

**제약**:
- 어댑터 금요일(5/15) 수령 (택배함 안전 보관 / 사무실 강행 비효율)
- KAIST 화/목 13~18시 + 수 재택 → 주당 가용 시간 제한
- **대표님 출장 중** → 셀프 판단 필요

---

## 2. 현재 자원

### 부품 5종 (사무실 보관, 지난주 공장에서 가져옴)

**v2 업데이트 (2026-05-11)**: pose_enumerator.py로 STL 자세 자동 분석 완료.
**v2.1 업데이트 (2026-05-11 오후)**: 핸드폰 사진 5종 × 3컷 + P3 캘리퍼스 실측 (56mm) 완료. STL 추정 정정.

| ID | 사진 식별 | **확정/추정 STL** | extents (mm) | 안정 자세 | top-3 | 난이도 | 신뢰도 |
|----|---------|----------------|------------|---------|------|------|------|
| P5 | 베이스 + 윙 + 다공 | **`main_body`** ⭐ | 25×32×6 | 4자세 (A·B 대칭) | 87% | 중 | **상 (거의 확정)** |
| P3 | L자 + 박스 공간 + 슬롯 | **`bracket_sen_1`** ⭐ | **15×56×53** ✅ 실측 일치 | (29종 표 참조) | - | 중 | **상 (실측 확정)** |
| P1 | 고리 + 막대 | `guide_paper_roll_cover_*` | 28×48×59 | 4자세 | 85% | 하 | 중 |
| P2 | T자 + 마운팅 박스 | `bracket_sensor1` 또는 `16_cam_f_bracket` | 15×26×42 또는 38×20×28 | 5자세 | 72% | 중 | 중 (L4 매칭으로 확정) |
| P4 | 곡선 띠 + 홀 3개 + 발 | `r_guide_a_r/l` 또는 `plate_e` | 118~163×40×34 또는 45×56×20 | 3~6자세 | 70~90% | 하 | 중 (L4 매칭으로 확정) |

**🔥 v2.1 새로 확정된 사실**:
- ✅ **P3 캘리퍼스 실측 56mm** → `bracket_sen_1.stl` (15×56×53mm) 거의 확정
- ✅ **STL 단위 의심 해소**: bracket_case (10×5×6mm)가 아니라 bracket_sen_1 (15×56×53mm). **모든 STL mm 단위 신뢰 가능**
- ✅ **레진 = Grey 통일** (사용자 확정). 표면 = 무광 ("잉크색"). ToF 반사 노이즈 우려 ↓
- ✅ **P5 = main_body 거의 확정** (1pager v1 추정 완벽 일치)
- ⚠️ **4/22 D435 케이스 연관**: 그때 매칭 실패한 부품이 P3와 같은 bracket_sen_1 가능성. Basler로 재시도 가능
- 추정 부정 (v1):
  - ④번 bracket_case 추정 → 실제 bracket_sen_1
  - ②번 "5+ 불안정" 추정 → 실제 4자세 단순

**29종 전체 통계** (참고):
- 매우 단순 (top-3 ≥ 90%): 6개 / 단순: 14개 / 중간: 9개 / **복잡(top-3 < 50%): 0개**
- → X/Y 각도 처리가 우려보다 simpler. 자세 분류기 ~5 클래스로 충분

**5종 데이터 수집 단순화 효과**:
- 레진 통일 → 조명 변형 우선순위 ↓ (다른 레진별 파라미터 분기 불필요)
- 표면 무광 → ToF depth 품질 양호 예상
- STL 단위 확인 → SizeFilter 신뢰 가능

> 사진 자료: 손에 든 컷 + 위에서 컷 × 2 = 부품당 3장, 총 15장
> P3 캘리퍼스 사진: 56mm 측정값 명확
> 자세 자동 분석 결과: `bin_picking/config/stable_poses.yaml` (5종), `stable_poses_all29.yaml` (29종)

### 카메라
- **D435** — 사무실에 있음 (대표님 USB 3.0 C-to-C 케이블 필요)
- **Basler Blaze-112 + ace2** — 사무실 보관, 어댑터 도착 후 라이브 (금 5/15)

### 코드 (4/10 완성)
- L1~L6 파이프라인 (FPFH + RANSAC + ICP, 6DoF 변환행렬 산출)
- grasp_database.yaml 29종
- Modbus INT16 서버 (Reg 130~140)
- W3+ synthetic 결과: easy 100% / crowded 90% / hard 60%
- `test_basler_live.py` (5/11 작성, 어댑터 도착 시 1줄 검증)

### 추가 부품 (29종 풀 세트)
- 대표님이 "공장 어딘가에 출력해뒀다" → 위치 불명
- **5종으로 SOP 확립 후, 시간 나면 공장 둘러보기**

---

## 3. 3-Layer 학습 데이터 전략

### Layer 1 — 안정 자세 Enumeration (카메라 무관, 지금 가능)

**입력**: STL 파일
**알고리즘**: trimesh convex hull → 각 face의 COM 투영 안쪽 여부 → 안정 자세 후보
**출력 형식** (`stable_poses.yaml`):
```yaml
01_sol_block_a:
  stable_poses:
    - id: A
      rotation_xyz: [0, 0, 0]
      probability: 0.55       # 빈에 던졌을 때 이 자세로 멈출 확률
      pickable: true
      grasp_ids: [g1, g2]
    - id: B
      rotation_xyz: [90, 0, 0]
      probability: 0.30
      pickable: true
      grasp_ids: [g3]
    - id: C
      rotation_xyz: [0, 90, 0]
      probability: 0.15
      pickable: false          # ← 뒤집어야 함
      regrasp_to: A
```

**검증**: 실물 부품 던지기 10~20회 → 시뮬 확률과 실측 비교

### Layer 2 — 다각도 촬영 (어댑터 후)

**부품 1종당**:
- yaw 0~360° (15° step = 24장)
- pitch 0~90° (30° step = 4장)
- 조명 3 × 배경 3 → **총 ~500장**

**셋업**:
```
[Basler 오버헤드 60~80cm 고정]
        ↓
[회전대 (자작 또는 구매)]
        ↓
[부품 1개]
```

**출력 구조**:
```
dataset/<part_id>/pose_<id>/
  img_000_rgb.png      # ace2
  img_000_depth.npy    # Blaze
  img_000_meta.json    # {yaw, pitch, light, occlusion}
```

### Layer 3 — 자동 라벨링

**파이프라인**:
```
RGB-D 캡처 → L1~L4 (FPFH+ICP) → GT pose 산출
    ↓
RMSE < 1.5mm   → 자동 라벨 ✅
RMSE ≥ 1.5mm   → 수동 보정 큐
```

**가능 이유**: 단독 부품 + 회전대 = easy 시나리오 → 현재 코드 100% 인식 (W3+ 결과)

---

## 4. ⭐ X/Y 각도 (대표님 #3) 처리안

대표님 인용: *"빈피킹 시 물체가 누워있거나 각도가 다르면 어떻게 뒤집는지? X/Y 각도가 중요한데 이에 필요한 데이터가 무엇인지 잘 고민할 것"*

**3가지 깔린 질문 → 답안**:

| 질문 | 답 |
|------|-----|
| (a) 자세 판별 어떻게? | Layer 1의 `stable_pose_id` (FPFH+ICP 6DoF로 rotation 분해 → 자세 분류기) |
| (b) 뒤집어야 픽 가능한 자세면 누가 뒤집나? | **펜던트 영역** (한솔 협의 필요). 우리는 `regrasp_to: A` 명시까지만 |
| (c) X/Y 회전 안정성을 위한 학습 데이터? | Layer 2 다각도 촬영 + Layer 3 GT pose 라벨 (부품ID + stable_pose_id + 6DoF) |

**데이터 라벨링 형식**:
```python
label = {
  "part_id": "05_plate_e",
  "stable_pose_id": "A",   # or "B"
  "T_world": [4x4 matrix],  # 6DoF GT pose
  "rmse": 0.8,
}
```

**5종별 X/Y 각도 시나리오**:
| 부품 | 자세 수 | 뒤집기 필요? | 비고 |
|------|--------|------------|------|
| ⑤ plate_e | 2 | ✅ (앞↔뒤) | 가장 단순 케이스 |
| ④ bracket_case | 2~3 | 부분적 | 큰 평면 OK |
| ① main_body | 2~3 | 부분적 | 특징점 풍부 |
| ③ cam_f_bracket | 3~4 | 부분적 | SizeFilter 검증용 |
| ② guide_paper_cover | **5+** | ✅ 다축 | 가장 어려운 케이스 ⚠️ |

---

## 5. 목표 데이터셋 (v2.4: 차원 축소 옵션 추가)

### 5.1 풀 규모 (원안 v2)

| 부품 | 자세 (실측) | 장수/자세 | 합계 | 비고 |
|------|-----------|----------|------|------|
| ⑤ plate_e | 3 | ~150 | 450 | top-3 90% = 가장 단순, SOP 검증 1순위 |
| ① main_body | 4 (A·B 통합) → **3** | ~150 | 450 | 대칭으로 라벨 통합 (실제 3자세 취급) |
| ④ bracket_case | 4 | ~110 | 440 | 단위 확인 필요 |
| ② guide_paper_cover | 4 | ~110 | 440 | 추정 틀려 부담 ↓ |
| ③ cam_f_bracket | 5 | ~90 | 450 | top-3 72%, 자세 분류 정확도 중요 |
| **합계** | **19자세** | | **~2,230장** |

### 5.2 차원 축소 옵션 (6/2 마감 안전 가정, **권장**)

사무실 가용 4~5일 = ~30시간 부족 가능성. 차원 축소로 **~1,200장 목표**:

| 차원 | 풀 (v2) | 축소 (v2.4) | 영향 |
|---|---|---|---|
| yaw | 24개 (15° step) | **12개 (30° step)** | 회전 다양성 절반 |
| 조명 | 3개 (normal/low/side) | **2개 (normal + low)** | side 는 ToF 그림자 약점 |
| 배경 | 3개 (white/dark/mixed) | **2개 (white + dark)** | mixed 는 단독 부품 가정 깨짐 |
| 자세 | 19자세 | 19자세 (유지) | 자세 다양성은 학습 핵심이라 유지 |

축소 데이터셋: 19자세 × 평균 60장 ≈ **1,140장**. 5/15~6/1 안에 충분.

→ 부트캠프 주제에 따라 풀 (v2) vs 축소 (v2.4) 결정. **W21 (5/25) 시점 데이터 진척 + 주제 함께 결정**.

상세 절차: [docs/binpicking_capture_sop_20260511.md](binpicking_capture_sop_20260511.md) (v1 → v1.1, 5/13)

---

## 6. 실험 계획 (v2.4)

### 5/11~12 — 인프라 완성 ✅
- 5/11: 부품 5종 사진/실측 + 사전 디벨롭 코드 ~1,900줄 + 어댑터 조기 도착
- 5/12: Mac Blaze 풀 작동 + 라이브 뷰어 + SOP v1 + 1pager v2.3

### 5/13~14 (재택) — 학습 데이터 라벨 신뢰도 인프라 ✅ + ⏳
- stable_poses.yaml 스키마 확장 (human_label / symmetry_groups) ✅
- auto_label.py 대칭 그룹 처리 (canonicalize_pose_id) ✅
- pose_validation_protocol.md (5/15 첫 30분 매뉴얼) ✅
- SOP v1.1 (REVIEW 큐 / 흔들림 검증 / 조명 valid % / L4 강제) ✅
- check_intrinsics_planar.py (A4 평면 RMS sanity) ⏳ 5/14
- capture_session.py (yaw sweep wrapper) ⏳ 5/14
- auto_label.py intrinsics_version 필드 ⏳ 5/14

### 5/15 (금, 사무실) — 본 캡처 진입 ⭐

| 시간 | 작업 |
|---|---|
| 9:00 | 카메라 셋업 (60~80cm, BASLER_BLAZE_IP=192.168.20.10) |
| 9:15 | 라이브 뷰어로 시야 + valid % 70%+ 확인 |
| 9:30 | **A4 평면 sanity check** (`check_intrinsics_planar.py`) — RMS < 2mm 확인 |
| 10:00 | **부품 자세 던지기 검증** (`pose_validation_protocol.md`) — 5종 × 10회 → yaml null 채우기 + 핸드폰 사진 |
| 11:30 | P5 main_body 자세 A 시범 5장 → auto_label 확인 |
| 13:00 | P5 자세 A 풀 yaw sweep (`capture_session.py --part main_body --pose A`) |
| 14:00 | **ACCEPT 80%+ 확인** — 미만이면 디버깅 / 80%+면 자세 B/C 추가 |
| 17:00 | 결과 분석 + 5/19~ 본격 5종 수집 계획 |

### 5/18~6/1 — 본격 5종 풀 데이터셋

| 일자 | 목표 |
|---|---|
| 월 5/18 | P5 풀 데이터셋 완성 + P3 또는 P4 시작 |
| 금 5/22 | 추가 부품 1~2종 (예승님 방문 일정 겹치면 E2E 우선) |
| 월 5/25 | 나머지 부품 + **부트캠프 주제 결정** (데이터 진척 함께) |
| 금 5/29 | 부족분 보충 + **미니 학습 sanity check** (1종 데이터로 1 epoch) |
| 월 6/1 | 데이터셋 v1 최종 검증 + 부트캠프 입력 자료 정리 |

### 6/2~7/9 (6주) — 부트캠프 본 프로젝트
- W21 결정한 주제로 진행
- 우리 데이터셋 v1 + 1pager 입력
- 후보: 6DoF pose estimation / Stable pose classification / cluttered scene 인식

### 6~7월 (병행) — 펜던트 통합
- 한솔/한화 패키지 답 수신 후 HCR-10L 펜던트 구조 받기
- 빈피킹 + 바텀비전 동시 운영 시퀀스 설계

---

## 7. 셀프 판단 영역 (대표님 부재 중)

### ✅ 자율 진행 OK (지금 결정)
- 5종 깊게 모드 (29종 얕게 X)
- D435로 사전 실험
- 데이터셋 형식 / 자동 라벨링 임계값 (RMSE 1.5mm) / 회전대 자작
- `test_basler_live.py` 작성 등 코드 인프라
- 회전대 자작 (책상 회전판 + 각도 디스크 등)

### ⏳ 초안만 작성 + align 대기
- ⭐ `stable_poses.yaml` (Layer 1 명세) — 5종 우선
- ⭐ regrasp 시퀀스 책임자 (우리 / 한솔 / 사람 / fixture?)
- ⭐ 학습 모델 선택 (PoseCNN vs PVN3D vs ICP augmentation)
- 5종 풀 데이터셋 규모 (각 500장 vs 1000장)
- KAIST 3단계 프로젝트 연계 여부

### ❌ 절대 안 함
- 외부 발주 (어댑터 외)
- 한솔 인터페이스 임의 변경
- 좌표 출력 형식 확정 (한화 패키지 답 대기)
- 펜던트 프로그램 우리 단독 결정

---

## 8. 리스크 + 대응

| # | 리스크 | 가능성 | 대응 |
|---|--------|-------|------|
| 1 | 펜던트 통합 = 한솔/한화 협의 미해결 | 중 | 6~7월에 본 작업. 지금은 빈피킹 출력만 깔끔하게 |
| 2 | D435 시도 시 4/22 USB 20cm 재현 | **확인됨** | 5/11 D435 케이블 짧음 확인 → **전략 A (코드 몰빵) 전환**, D435 실험 보류 |
| 3 | 어댑터 사양 미달 | 저 | 환불 + UGREEN 재발주. SOP+코드 자산은 유지 |
| 4 | 5종으로 학습 데이터 부족 | 중 | 5종 SOP 확립 → 29종 부품 추후 확보 시 동일 SOP 적용 |
| 5 | 대표님 align 어긋남 | 중 | 본 1pager로 align. 출장 복귀 시 즉시 전송 |
| 6 | 실 부품 CAD 불일치 | 저 | 4/22 발견 패턴 (SizeFilter Z 50% 오차) — 실측으로 검증 |
| 7 | KAIST + 빈피킹 동시 진행 시간 부족 | 중 | 5월 SOP 확립 후 6월 KAIST 3단계 프로젝트로 통합 |
| 8 | **BLAZE/ACE2 intrinsics 추정값 부정확** | 중 | **5/14 갱신**: `check_intrinsics_planar.py` 로 5/15 사무실 도착 즉시 A4 평면 RMS 검증 (< 2mm = OK, > 5mm = ChArUco 캘리브 필요). intrinsics_version="estimated_v2_20260513" 모든 라벨에 박힘 → 추후 캘리브 후 재라벨 가능 |
| 9 | **① main_body 180° 대칭** | 저 | 학습 라벨 A·B 통합 처리. 자세 4개 → 실질 3개 취급 |
| ~~10~~ | ~~④ bracket_case 단위 의심 (10×5×6mm)~~ | ✅ **해소 (5/11)** | P3 캘리퍼스 실측 56mm → bracket_case가 아니라 **bracket_sen_1 (15×56×53mm) 확정**. STL 단위 mm 신뢰. grasp_database 재생성 불필요 |
| 11 | P2/P4 STL 미확정 (2개 후보) | 저 | L4 매칭 시 자동 확정 (RMSE/fitness로 1개 결정) |
| 12 | 4/22 D435 매칭 실패 부품 재출현 가능성 | 저 | P3 = bracket_sen_1 → 4/22 매칭 실패 부품과 같음. Basler 60~80cm로 재시도 시 인식 가능 예상 |
| 13 | **ACE2 렌즈 초점거리 미확정** (한솔 보유) | 중 | 현재 코드 12mm 렌즈 가정 (fx=3478). 한솔 단톡 답 받으면 정정: 8mm → 2319 / 16mm → 4638. 답 대기 중 Blaze 단독 (--no-ace2)으로 데이터 수집 가능 |
| 14 | Basler GigE에 sudo 잘못 사용 시 권한 혼선 | 저 | RealSense D435 (USB raw) 패턴 잘못 적용 위험. SOP/test_basler_live 모두 sudo 없이 (5/11 정정) |
| ~~15~~ | ~~macOS Blaze Supplementary 미지원 → Mac에서 못 씀 가설~~ | ✅ **해소 (5/12)** | pypylon만으로 Blaze-112 풀 작동 확인. ProducerGEV.cti + BaslerGigE TL 사용 + Range component만 enable + Mono16 raw로 깨끗한 848×480 uint16 mm depth. IPC-510 대기 불필요 |
| 16 | macOS EnumerateDevices() Blaze 미동작 | 저 | 워크어라운드 적용됨 (commit 7e28df9): 환경변수 BASLER_BLAZE_IP 또는 인자로 IP 직접 fallback. 시리얼/모델 매칭 인터페이스 보존 |
| **17** | **데이터셋 silent bias** — auto_label REVIEW 큐 무시 시 어려운 자세 underrepresented → 학습 모델이 그 자세 못 풀게 됨. "ACCEPT 80%" 지표가 거꾸로 위험 신호일 수 있음 | **중** | SOP v1.1 § 5.1 (5/13 신규): REVIEW 비율 20~40% 면 사람 검수 큐 / > 40% 면 셋업 디버깅. 자세 분포 (ACCEPT) vs yaml probability ±20% 비교. 어려운 자세는 수동 GT 라벨 입력 |
| **18** | **단독 부품 도메인 갭** — 학습 데이터 = single-instance / 실 빈피킹 = cluttered + occlusion. 이대로 학습하면 single-instance pose model 만 잘 됨 | **중** | 6월 부트캠프 주제 결정 시 합성 데이터 (BlenderProc cluttered scene) 보강 검토. 또는 5/29 미니 학습 sanity check 시 실 빈피킹 시나리오 1~2장 테스트 |

---

## 9. 대표님께 질의/Confirm 필요 (복귀 시)

1. **학습 데이터 규모** — 5종 × ~500장 = 2,400장 적정한가? 부족하면 1000장씩?
2. **regrasp 시퀀스 책임 소재** — 우리 코드에서 명시? 한솔 펜던트가 처리? 사람이 손으로?
3. **학습 모델 선택 시점** — 데이터 모인 후? 아니면 지금 KAIST 3단계 프로젝트로 묶기?
4. **29종 풀 데이터셋 시점** — 공장 출력 부품 위치 확인은 누가 / 언제?
5. **펜던트 통합 일정** — 한화 패키지 답 ASAP는 우리가 push? 한솔 push?
6. **빈피킹 우선순위** — Phase 4 MaixCAM 보다 우선 유지? KAIST 와 충돌 시 어느 쪽?

---

## 10. 의사결정 기록 (Decision Log)

| 일자 | 결정 | 이유 |
|------|------|------|
| 5/6 | 6DoF → 4DoF 좌표 출력 | 한솔 회의, 다면은 자세 분리로 |
| 5/8 | 어댑터 ipTIME U1G-C 1개 발주 | AMCA017 사양 미달, ace2 부품은 한솔 보유 |
| 5/11 | **29종 → 5종 깊게 모드** | 부품 위치 불명 + 대표님 부재. SOP가 부품 수보다 자산 |
| 5/11 (오전) | D+B 전략 잠정 추천 | 사전 디벨롭 코드는 카메라 도착 후 어차피 재수정. 1pager+실데이터가 더 강함 |
| 5/11 | 어댑터 금요일 수령 (화 사무실 강행 X) | 수 재택이라 차이 1일로 축소 |
| 5/11 | **부품 5개 시범 순서**: ⑤ → ④ → ① → ③ → ② | 단순한 것부터 (뒤집기 케이스도 단순) |
| 5/11 (오후) | **D435 USB 케이블 = 4/22와 같은 짧은 케이블 확인** | 4/22 USB 20cm 재현 위험 |
| 5/11 (오후) | **전략 A 전환 (코드 작업 몰빵)** | D435 어색 셋업 < 4일 후 Basler 정상 셋업. 이중 작업 회피 |
| 5/11 | **ACE2 모델명 정정 a2A2590 → a2A2448-23gcBAS** | 5/8 박스 개봉 시 실 모델 확인 (코드 5개 파일 수정) |
| 5/11 | **BLAZE intrinsics 정정 460/460 → 417/188** | FOV 75°×104° 기반 재계산 (검산 PASS) |
| 5/11 | **부품 5종 자세 자동 분석 (pose_enumerator.py)** | 추정 → 실측. ② 추정 틀림, ① 대칭, ④ 단위 의심 발견 |
| 5/11 | **부품 실측 스킵 (L4 매칭으로 자동 확정)** | 임시 ID(①~⑤)로 진행, 캡처 후 L4 결과로 부품명 확정 |
| 5/11 (오후) | **부품 5종 핸드폰 사진 15장 (3컷 × 5)** | 업무일지 가시적 자료 + STL 사전 매칭 추정 가능 |
| 5/11 (오후) | **P3 캘리퍼스 실측 56mm** | bracket_case 단위 의심 해소 → bracket_sen_1 확정. STL 모든 단위 mm 신뢰 |
| 5/11 (오후) | **레진 Grey 통일 + 무광 표면 확정** | 조명 변형 우선순위 ↓, ToF 반사 노이즈 우려 ↓, 데이터 수집 SOP 단순화 |
| 5/11 (오후) | **회전대 자작 vs 다이소 → 사용자 결정 보류** | SOP § 1.2에 옵션 A(없이) + B(다이소) 둘 다 기록. auto_label.py가 yaw 자동 산출하므로 필수 아님 |
| 5/11 (오후) | **🎉 어댑터 ipTIME U1G-C 조기 도착** (예상 5/15 → 5/11, 4일 빠름) | Mac 검증 Step 1~3 즉시 PASS (USB 5Gb/s + 1000baseT + IP 192.168.10.1). 데이터 수집 진입 4일 빠름 |
| 5/11 (오후) | **Basler GigE = sudo 불필요 정정** | 메모리 § 4/13 D435 (USB raw access 차단) 패턴을 Basler에 적용하면 안 됨. test_basler_live.py + SOP 모두 sudo 없이 |
| 5/11 (오후) | **Mac ↔ 6000 Claude 릴레이 양식 정식 채택** | `feedback_mac_6000_relay.md` (6000) + `feedback_server_relay_messages.md` (Mac). 환경 전환 시 동기화 메시지 필수 |
| 5/11 (오후) | **commit 9a2fafd push origin main only** (personal/한솔 미러 제외) | 1pager § 7 셀프 판단 영역 + § 10 의사결정 = 내부 자료. 한솔 미러 노출 부적절. orinu-ai Private repo만 OK |
| 5/12 | **🎉 Mac Blaze 풀 작동 검증 (옵션 1 성공)** | pypylon 단독으로 Blaze-112 풀 작동 (Supplementary 없이). IP fallback + Range component + Mono16. test_basler_live.py --live --save PASS (480×848 uint16, 유니크 382). IPC-510 대기 3주 불필요 |
| 5/12 | **BLAZE 실측 정정: 848×480 (매뉴얼 640 오류)** | 5/8 박스 매뉴얼 640×480 가정이 사실은 native 848×480. fx 417 → **553** 재계산. cx 320 → 424. 향후 정식 캘리브 시 추가 정정 가능 |
| 5/12 | **Mac 네트워크 영구 분리: 192.168.20/24** | 사무실 Wi-Fi (192.168.10/24)와 충돌 회피. 어댑터 en8 + Blaze 전용 서브넷. ping 11~76ms → 1.6~2.7ms (6~30배 빠름). Wi-Fi 켠 채 카메라 작업 가능 |
| 5/12 | **Push 정책 명확화 — 모든 commit dual push (origin + personal)** | 사용자 기존 운영 방식 = 모든 파일 dual. 5/11 commit 9a2fafd "personal 제외"는 예외였고 정상 패턴 X. 정책: 모든 push = orinu-ai (origin) + m2222n (personal) 동시. 보안은 외부 유출 시점(스크린샷/카톡/PDF)에서 CLAUDE.md § 보안 원칙 적용. credentials/.env는 .gitignore로 보호 |
| 5/13~14 | **학습 데이터 라벨 신뢰도 인프라 — 외부 커뮤니케이션 3건 발송 보류** | 사용자 결정: ACE2 단톡 + 예승님 카톡 + 1pager 대표님 메시지 발송 시점 자율 결정. 재택 시간 = 인프라 보강에 집중. 결과: stable_poses 스키마 확장 (human_label/symmetry_groups) + auto_label 대칭 그룹 (canonicalize_pose_id) + pose_validation_protocol.md (5/15 매뉴얼) + SOP v1.1 (REVIEW/흔들림/조명 valid %/L4 강제) + check_intrinsics_planar.py (A4 평면 sanity) + capture_session.py (yaw sweep wrapper) + intrinsics_version 라벨 추적 |
| 5/14 | **6/2 KAIST 3단계 부트캠프 회사 데이터 프로젝트 마감 도입** | 준비 21일 (5/13~6/1), 사무실 가용 4~5일. 목표 데이터 1,200~2,400장 (차원 축소 옵션). 주제 결정 W21 (5/25~) — 데이터 진척 함께 결정. § 0 신규 절 추가 |
| 5/14 | **목표 데이터셋 차원 축소 옵션 권장** | 사무실 가용 4~5일 = ~30시간 부족 위험. yaw 24→12 + 조명 3→2 + 배경 3→2 = 1종 380→200장, 5종 ~1,140장. 자세 다양성 유지 (학습 핵심). § 5.2 신규 |
| 5/14 | **5/15 일정 재조정: "P5 풀 자세" → "P5 자세 A만 풀, B/C 시간 남으면"** | 첫 캡처 셋업 시행착오 시간 보수적 확보. ACCEPT 80% 미만이면 오후 디버깅. 80%+면 자세 B/C 추가. 사용자 결정 |

---

## 11. 산출물 인벤토리 (5/11 + 5/12 + 5/13~14, 인프라 완성)

### 코드 (9개 — 5/13~14 추가: check_intrinsics_planar / capture_session / intrinsics_version 추적)
| 파일 | 줄수 | 역할 |
|------|------|------|
| `bin_picking/tests/test_basler_live.py` | 678 | 어댑터 검증 (--discover/--live/--save/--load/--pipeline) |
| `bin_picking/tests/live_viewer_basler.py` (5/12) | 179 | Mac 인터랙티브 라이브 뷰어 (cv2 + pypylon). 시야 확인 + 부품 배치 조절 |
| `bin_picking/tests/check_intrinsics_planar.py` ⭐ 신규 (5/14) | ~280 | A4 평면 RANSAC fit → intrinsics 추정값 검증 (RMS < 2mm = PASS). 5/15 첫 단계 |
| `bin_picking/tests/capture_session.py` ⭐ 신규 (5/14) | ~290 | yaw sweep wrapper. 부품/자세/조명/배경 + 진행 카운터 + 중단/재개 + 자동 meta 갱신 |
| `bin_picking/src/recognition/pose_enumerator.py` (5/13 v1.1) | 480 | STL → 안정 자세 yaml + **human_label/symmetry_groups 필드 신규** |
| `bin_picking/src/labeling/auto_label.py` (5/13 대칭 + 5/14 intrinsics_version) | 880 | 자동 라벨링 + **canonicalize_pose_id (대칭 그룹) + intrinsics_version 라벨**. simulate PASS |
| `bin_picking/src/acquisition/basler_capture.py` (5/13~14) | 600+ | BLAZE 정정 + IP fallback + Range/Mono16 + **INTRINSICS_VERSION 상수** |
| `bin_picking/src/acquisition/{depth_to_pointcloud, hand_eye_calibration}.py` 등 | - | BLAZE intrinsics 일관성 |

### 설정 (2개)
| 파일 | 크기 | 역할 |
|------|------|------|
| `bin_picking/config/stable_poses.yaml` (5/13 v1.1) | 11 KB | 5종 안정 자세 + 신규 필드 (human_label/symmetry_groups/pickable/regrasp_to) |
| `bin_picking/config/stable_poses_all29.yaml` (5/13 v1.1) | 64 KB | 29종 전체 + 신규 필드 |

### 문서 (4개 — pose_validation_protocol 신규)
| 파일 | 역할 |
|------|------|
| `docs/binpicking_learning_data_strategy_1pager_20260511.md` (v2.4) | **본 1pager** (전략 + 6/2 마감) |
| `docs/binpicking_capture_sop_20260511.md` (v1.1) | 데이터 수집 SOP + **§ 5.1 REVIEW 큐 처리 / § 1.3 조명 valid % / § 2.1 L4 강제 / § 4.1 흔들림 검증** |
| `docs/binpicking_pose_validation_protocol.md` ⭐ 신규 (5/13) | **5/15 첫 30분 부품 던지기 검증 매뉴얼** (yaml null 채우기) |
| `docs/hansol_handover/bottom_vision_interface_notes_20260511.md` | 한솔 바텀비전 인터페이스 명세 |

### 메모리 (4개)
| 파일 | 역할 |
|------|------|
| `memory/project_binpicking_5parts_strategy.md` | 5종 깊게 모드 |
| `memory/project_binpicking_predev_codes_0511.md` | 사전 디벨롭 작업 기록 (5/11~14) |
| `memory/project_week_plan_0511.md` (5/14 갱신) | W19 일정 + 5/15 재조정 + 6/2 마감 |
| `memory/project_bottom_vision_handover_done.md` | 바텀비전 인수 완료 |

---

## 14. 학습 데이터 라벨 신뢰도 체크리스트 (5/15 본 캡처 직전 자가 점검)

> 이 체크리스트 통과 없이 본 캡처 들어가면 **데이터 통째로 재라벨 위험**.

### 사무실 도착 직후 (9:00~10:00)
- [ ] 카메라 60~80cm 고정 (책장/모니터/삼각대 흔들림 없음)
- [ ] BASLER_BLAZE_IP=192.168.20.10 환경변수 export
- [ ] 라이브 뷰어로 시야 + valid % 70%+ 확인 (`live_viewer_basler.py`)
- [ ] **A4 평면 sanity check 통과** (RMS < 2mm, `check_intrinsics_planar.py`)
- [ ] **부품 5종 자세 던지기 검증 완료** (`pose_validation_protocol.md` Step 1~6)
  - [ ] yaml `human_label` 채워짐 (부품 + 자세별)
  - [ ] yaml `symmetry_groups` 결정됨 (대칭이면 묶기, 아니면 명시적 null)
  - [ ] yaml `pickable` / `regrasp_to` 채워짐 (불확실하면 null 유지)
  - [ ] 핸드폰 사진 (자세 id ↔ 외관) 기록됨

### 첫 캡처 직후 (11:30~12:00)
- [ ] auto_label.py `--part main_body` 강제 (L4 후보 좁히기, SOP § 2.1)
- [ ] ACCEPT 비율 ≥ 80% (5장 시범에서)
- [ ] 라벨 json 에 `intrinsics_version` 박혀 있음 (5/14 추가 필드)
- [ ] 자세 id 가 사람 직관과 일치 (사진 vs yaml human_label 비교)

### 본 캡처 진입 후 매 자세 (24장 끝날 때마다)
- [ ] ACCEPT 자세 분포 vs yaml `probability` ±20% 이내 (SOP § 5.1)
- [ ] REVIEW 사유 분포 확인 (rmse_high 가 다수면 intrinsics 의심)
- [ ] depth 유니크 값 > 30 (양자화 X, SOP § 4.1)
- [ ] 카메라 흔들림 검증 통과 (회전대 옵션 A 시 부품 없이 5장 RMS)

### 본 캡처 종료 후 (저녁)
- [ ] 5/19~ 일정 계획 (남은 부품 우선순위)
- [ ] dataset_v1 폴더 구조 정상 (부품/자세/{accept,review,fail})
- [ ] dual push (origin + personal)
- [ ] 메모리 갱신 (week_plan_0511 + MEMORY.md P0)

---

## 12. Mac ↔ 6000 환경 분담 (5/11 확정)

| 환경 | 역할 | 의존성 |
|------|------|------|
| **Mac 로컬** | 카메라 데이터 수집 + Open3D 파이프라인 실행 + pylon GUI + 어댑터 검증 | Open3D ✅ (AVX2), pypylon 26.4.1, 카메라 직접 |
| **6000 서버** | 코드 저장소 + git push/pull + sandbox + 메모리 관리 + 문서 | Open3D ❌ (AVX2 미지원), pypylon 26.03.1 (smoke만), 카메라 X |
| **비전 PC (IPC-510)** | 본 운영 (5월 후반 ~) | Linux, pylon Suite 필요, 한솔 바텀비전 동거 |

### 운영 주의 (5/11 정정)

- **Basler GigE = sudo 불필요** (이더넷 통신, USB raw access 제약 없음)
- RealSense D435 (USB)의 sudo 패턴을 Basler에 적용 X
- `test_basler_live.py`, `auto_label.py` 모두 `python ...` (sudo 없이) 실행

### 환경 전환 시 절차

1. **6000 → Mac**: 새 코드 commit + push (orinu-ai만, personal/한솔 미러 보안 검토 후)
2. **Mac**: `git pull origin main` + venv 확인 + 작업
3. **Mac → 6000**: 카메라 실험 결과/메모리 갱신 필요 시 릴레이 메시지로 알림

### 릴레이 메시지 양식

`memory/feedback_mac_6000_relay.md` (6000) / `feedback_server_relay_messages.md` (Mac) — 5/11 합의:
- 환경 / 검증 / 다음 단계 / 상대 측 영향 / 룰

---

## 참고 문서

- 대표님 지시 원문: `memory/project_binpicking_ceo_directive_0506.md`
- 빈피킹 전체 상태: `memory/project_binpicking.md`
- 5종 전략 상세: `memory/project_binpicking_5parts_strategy.md`
- 사전 디벨롭 (5/11): `memory/project_binpicking_predev_codes_0511.md`
- 이번주 계획: `memory/project_week_plan_0511.md`
- 5/6 한솔 회의록: `memory/project_meeting_0506_hansol.md`
- 바텀비전 인터페이스: `docs/hansol_handover/bottom_vision_interface_notes_20260511.md`
- **데이터 수집 SOP**: `docs/binpicking_capture_sop_20260511.md` ⭐
- 4/14 HCR 교육 (Modbus + 펜던트): `memory/reference_hcr_user_education.md`
