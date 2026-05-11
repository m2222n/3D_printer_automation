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

## 5. 목표 데이터셋 (v2: 실측 자세 수 반영)

| 부품 | 자세 (실측) | 장수/자세 | 합계 | 비고 |
|------|-----------|----------|------|------|
| ⑤ plate_e | 3 | ~150 | 450 | top-3 90% = 가장 단순, SOP 검증 1순위 |
| ① main_body | 4 (A·B 통합) → **3** | ~150 | 450 | 대칭으로 라벨 통합 (실제 3자세 취급) |
| ④ bracket_case | 4 | ~110 | 440 | 단위 확인 필요 |
| ② guide_paper_cover | 4 | ~110 | 440 | 추정 틀려 부담 ↓ |
| ③ cam_f_bracket | 5 | ~90 | 450 | top-3 72%, 자세 분류 정확도 중요 |
| **합계** | **19자세** | | **~2,230장** |

→ v1 (~2,440장)과 거의 동일. **자세 수 19개로 합리적 규모**.

### 촬영 변형 (자세 1개당)
- yaw 24개 (15° step, 회전대)
- pitch 2~4개 (선택, 부품 허용 자세)
- 조명 3개 (normal / low / side)
- 배경 3개 (white / dark / mixed)
- → 1자세당 50~150장 (조명·배경 조합 일부만)

상세 절차: `docs/binpicking_capture_sop_20260511.md` ⭐ 신규

---

## 6. 실험 계획

### 5/11 (월, 사무실) — D435로 워크플로우 검증
- 부품 5개 캘리퍼스 실측 + STL 매칭 → 이름 확정
- D435 셋업 + USB 케이블 확인 + 오버헤드 30~50cm 가능 여부
- 부품 1~2종 시범 (총 ~30장) — L1~L4 돌려서 인식률/RMSE 확인
- **목표**: 4/22 USB 20cm 제약 해결 여부 + SOP 초안

### 5/12~14 (화/목 KAIST, 수 재택) — D435 데이터 본격
- 부품 5종 × ~30장 = ~150장 (D435 prototype)
- 자동 라벨링 워크플로우 검증
- 1pager v2 (실험 결과 반영)

### 5/15 (금, 사무실) — 어댑터 수령 + Basler 라이브
- 8단계 검증 (`system_profiler` / `ifconfig` / pylon)
- Blaze 라이브 depth + ace2 RGB
- D435 SOP를 Basler에 적용 (카메라만 갈아끼움)
- 부품 1종 Basler 시범 (~50장)

### 5월 후반 — 5종 풀 데이터셋
- Basler로 부품 5종 × ~500장 = ~2,400장
- 자동 라벨링 적용
- 데이터셋 v1 완성

### 6월 — 학습 모델 검토
- 옵션 1: 실데이터 augmentation → ICP 강건화
- 옵션 2: PoseCNN / PVN3D / FoundationPose (1종당 1000+장 필요)
- KAIST 3단계 프로젝트 주제 후보

### 6~7월 — 펜던트 통합
- 한솔/한화 패키지 답 수신 후 HCR-10L 펜던트 구조 받기
- 빈피킹 + 바텀비전 동시 운영 시퀀스 설계
- 실 피킹 + 시뮬 토글 OFF E2E

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
| 8 | **BLAZE/ACE2 intrinsics 추정값 부정확** | 중 | 카메라 도착 후 ChAruco 보드로 정식 캘리브. 현재 **BLAZE fx=553/fy=188 (5/12 실측 정정: width 848 기반)**, ACE2 fx=3478 (12mm 렌즈 가정) |
| 9 | **① main_body 180° 대칭** | 저 | 학습 라벨 A·B 통합 처리. 자세 4개 → 실질 3개 취급 |
| ~~10~~ | ~~④ bracket_case 단위 의심 (10×5×6mm)~~ | ✅ **해소 (5/11)** | P3 캘리퍼스 실측 56mm → bracket_case가 아니라 **bracket_sen_1 (15×56×53mm) 확정**. STL 단위 mm 신뢰. grasp_database 재생성 불필요 |
| 11 | P2/P4 STL 미확정 (2개 후보) | 저 | L4 매칭 시 자동 확정 (RMSE/fitness로 1개 결정) |
| 12 | 4/22 D435 매칭 실패 부품 재출현 가능성 | 저 | P3 = bracket_sen_1 → 4/22 매칭 실패 부품과 같음. Basler 60~80cm로 재시도 시 인식 가능 예상 |
| 13 | **ACE2 렌즈 초점거리 미확정** (한솔 보유) | 중 | 현재 코드 12mm 렌즈 가정 (fx=3478). 한솔 단톡 답 받으면 정정: 8mm → 2319 / 16mm → 4638. 답 대기 중 Blaze 단독 (--no-ace2)으로 데이터 수집 가능 |
| 14 | Basler GigE에 sudo 잘못 사용 시 권한 혼선 | 저 | RealSense D435 (USB raw) 패턴 잘못 적용 위험. SOP/test_basler_live 모두 sudo 없이 (5/11 정정) |
| ~~15~~ | ~~macOS Blaze Supplementary 미지원 → Mac에서 못 씀 가설~~ | ✅ **해소 (5/12)** | pypylon만으로 Blaze-112 풀 작동 확인. ProducerGEV.cti + BaslerGigE TL 사용 + Range component만 enable + Mono16 raw로 깨끗한 848×480 uint16 mm depth. IPC-510 대기 불필요 |
| 16 | macOS EnumerateDevices() Blaze 미동작 | 저 | 워크어라운드 적용됨 (commit 7e28df9): 환경변수 BASLER_BLAZE_IP 또는 인자로 IP 직접 fallback. 시리얼/모델 매칭 인터페이스 보존 |

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

---

## 11. 산출물 인벤토리 (5/11 사전 디벨롭 + 5/12 인프라 완성)

### 코드 (6개 — 5/12 라이브 뷰어 추가)
| 파일 | 줄수 | 역할 |
|------|------|------|
| `bin_picking/tests/test_basler_live.py` | 678 | 어댑터 검증 (--discover/--live/--save/--load/--pipeline) |
| `bin_picking/tests/live_viewer_basler.py` ⭐ 신규 (5/12) | 179 | Mac 인터랙티브 라이브 뷰어 (cv2 + pypylon, pylon Viewer 미지원 회피). 키: ESC/q/s/c/r/+/-. 시야 확인 + 부품 배치 조절 |
| `bin_picking/src/recognition/pose_enumerator.py` | 412 | STL → 안정 자세 yaml 자동 생성 (5종 + 29종) |
| `bin_picking/src/labeling/auto_label.py` | 815 | 자동 라벨링 (L1~L4 + stable_pose 매핑 + 품질 게이트, 시뮬 PASS) |
| `bin_picking/src/acquisition/basler_capture.py` | 600+ (5/11+5/12 수정) | BLAZE 정정 (width 848 + fx 553 + cx 424) + IP fallback + Range/Mono16 |
| `bin_picking/src/acquisition/{depth_to_pointcloud, hand_eye_calibration}.py` 등 | - | BLAZE intrinsics 일관성 (5/11 + 5/12) |

### 설정 (2개)
| 파일 | 크기 | 역할 |
|------|------|------|
| `bin_picking/config/stable_poses.yaml` | 10 KB | 5종 안정 자세 (parts.{plate_e, bracket_case, ...}) |
| `bin_picking/config/stable_poses_all29.yaml` | 60 KB | 29종 전체 (향후 확장용 GT) |

### 문서 (3개)
| 파일 | 역할 |
|------|------|
| `docs/binpicking_learning_data_strategy_1pager_20260511.md` | **본 1pager** (전략) |
| `docs/binpicking_capture_sop_20260511.md` ⭐ 신규 | 데이터 수집 SOP (어댑터 도착 후 매뉴얼) |
| `docs/hansol_handover/bottom_vision_interface_notes_20260511.md` | 한솔 바텀비전 인터페이스 명세 |

### 메모리 (4개 신규/완료)
| 파일 | 역할 |
|------|------|
| `memory/project_binpicking_5parts_strategy.md` | 5종 깊게 모드 |
| `memory/project_binpicking_predev_codes_0511.md` | 사전 디벨롭 작업 기록 |
| `memory/project_week_plan_0511.md` | 이번주 일정 |
| `memory/project_bottom_vision_handover_done.md` | 바텀비전 인수 완료 |

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
