# 부품 안정 자세 검증 프로토콜 (5/15 첫 30분 매뉴얼)

**작성**: 2026-05-13 (재택 사전 디벨롭)
**적용 시점**: 5/15 (금) 사무실 도착 직후, 본 캡처 시작 전
**소요 시간**: 약 30~40분 (5종 부품 × 7~8분)
**목적**: `stable_poses.yaml` 의 자동 생성 자세 후보를 실물로 검증하고 사람 라벨 채우기

---

## 왜 필요한가

`stable_poses.yaml` 은 [pose_enumerator.py](../bin_picking/src/recognition/pose_enumerator.py) 가 trimesh의 convex hull + COM 알고리즘으로 자동 산출한 것입니다. **실물로 검증된 적이 없습니다**:

- 자세 id (A/B/C/...) 가 실제로 어떤 외관인지 사람이 본 적 없음
- `pickable`, `regrasp_to`, `symmetry_groups` 모두 `null` 상태
- yaml의 `probability` (안착 확률) 가 실측과 맞는지 모름

이 검증이 **데이터셋 라벨 신뢰의 90%를 좌우합니다**. `auto_label.py` 의 `find_closest_stable_pose` 가 yaml의 transform과 ICP 결과를 비교해서 자세 id를 붙이므로, **yaml이 사람 직관과 안 맞으면 학습 데이터가 통째로 어긋납니다**.

특히:
- **대칭 부품** (P5 main_body) — A·B 두 자세가 외관상 동일하면 라벨 통합 필수. 안 통합하면 학습 모델이 "같은 자세를 두 클래스로" 학습해 혼동
- **픽 불가 자세** — 그리퍼가 못 들어가는 자세는 학습 데이터에 포함해도 의미 없음 (regrasp 대상)
- **확률 검증** — yaml이 "이 자세 5% 확률" 이라고 했는데 실제 던지면 30% 나오면 yaml 신뢰도 의심

---

## 준비물

| 항목 | 비고 |
|---|---|
| 부품 5종 | P1~P5 (사무실 보관, 5/11 식별 완료) |
| 핸드폰 | 자세 id ↔ 외관 사진 매핑용 |
| 책상 (평평한 면) | 던지기 표면 |
| `stable_poses.yaml` 출력 | 노트북에서 옆에 열어놓기 |
| 펜 + 메모지 (선택) | yaml에 적기 전 임시 기록 |

---

## 절차 (부품 1종당 7~8분, 5종 합계 ~35분)

### Step 1 — yaml 자세 후보 확인 (1분)

[bin_picking/config/stable_poses.yaml](../bin_picking/config/stable_poses.yaml) 에서 해당 부품 섹션 열기. 예시 (P5 main_body):

```yaml
main_body:
  extents_mm: [25.0, 32.0, 6.0]
  human_label: null              # ← 여기 채울 것
  symmetry_groups: null          # ← 여기 채울 것
  stable_poses:
    - id: A
      probability: 0.403
      rotation_xyz_deg: [0, 0, 0]
      pickable: null             # ← 여기 채울 것
      regrasp_to: null           # ← 여기 채울 것
      human_label: null          # ← 여기 채울 것
    - id: B
      probability: 0.403         # ← A와 동일 확률 = 대칭 의심
      rotation_xyz_deg: [180, 0, 0]
      ...
```

→ **A·B 확률이 같으면 대칭 의심 신호**. Step 4에서 확인.

### Step 2 — 던지기 10회 (3분)

부품을 책상 위 약 10cm 위에서 자유낙하 10회. 매번 어느 자세로 멈추는지 관찰.

기록 형식 (메모지 or 머릿속):
```
P5 main_body 던지기 결과:
  A자세 (윙 위로): IIII II (7회)
  B자세 (윙 아래로): II (2회)
  C자세 (옆으로 서있음): I (1회)
  D자세: 0회
```

**판정 기준**:
- 실측 비율 vs yaml `probability` 가 ±20% 이내면 yaml 신뢰 OK
- 크게 어긋나면 (예: yaml에 0.40인데 실측 0회) yaml 재생성 검토 (5/15 본 캡처 후 결정)
- yaml에 없는 자세가 나오면 → `n_stable_poses_total` 보다 threshold 후 자세가 적어서 잘려 나간 것. 의미 있으면 yaml에 수동 추가

### Step 3 — 자세 ↔ 외관 매핑 (2분)

각 자세 id 에 대해 부품을 그 자세로 놓고:
- 핸드폰으로 위에서 1장, 옆에서 1장 촬영 (총 자세 N × 2장)
- 외관을 한 문장으로 묘사 → `stable_poses.yaml` 의 자세 레벨 `human_label` 에 기록

**human_label 작성 원칙**:
- 그리퍼/카메라 관점에서 무엇이 보이는지 (실 빈피킹 시점)
- 추상적 단어 X ("쓰러진 자세" X), 구체적 X ("윙 위로, 마운팅 홀 4개 보임" ✅)
- 한국어 OK, 영어 OK, 일관성만 유지

예시:
```yaml
main_body:
  human_label: "베이스 + 양쪽 윙 + 마운팅 홀 4개"
  stable_poses:
    - id: A
      human_label: "윙 위로, 마운팅 홀 4개 보임 (가장 흔한 자세)"
    - id: B
      human_label: "윙 아래로, 베이스 평면 위 (A와 180° 대칭)"
    - id: C
      human_label: "옆으로 서있음, 좁은 측면 보임"
    - id: D
      human_label: "다른 측면 서있음"
```

### Step 4 — 대칭 그룹 판정 (1분)

자세 둘 이상이 **외관상 구별 불가능** 하면 대칭 그룹:

판정 기준:
- 사진 봤을 때 어느 자세인지 사람이 못 맞히면 → 대칭
- 자세별 `probability` 가 거의 같으면 (±5% 이내) → 대칭 가능성 ↑
- 부품에 회전 대칭축이 있으면 (180°, 90°) → 그 회전축으로 통합되는 자세는 대칭

기록 형식:
```yaml
main_body:
  symmetry_groups:
    - ["A", "B"]   # A·B 는 180° 대칭, 외관 동일 → 학습 라벨 통합
```

**그룹 안 자세 = canonical id (첫 id) 로 통일**. `auto_label.py` 가 자동 처리합니다 (이미 구현됨).

⚠️ **대칭 그룹 잘못 묶으면 학습 데이터 손상 위험**. 의심되면 묶지 말고 빈 채로 두기. 5/15 본 캡처 후 다시 검토.

### Step 5 — pickable / regrasp_to 판정 (1분)

각 자세에 대해:

**pickable 기준** — 그리퍼가 위에서 접근해서 안정적으로 잡을 수 있는가?
- 그리퍼 (현재 미장착, 가상 판정) 가 자세 위쪽에서 접근 → 부품 폭 < 그리퍼 max stroke
- 마운팅 홀이나 평면을 잡을 수 있으면 ✅
- 부품이 옆으로 누워있는데 그리퍼 stroke 부족하면 ❌

**규칙**: 의심되면 `null` 유지 (그리퍼 미장착이라 정확 판정 불가). 5/27 그리퍼 도착 후 재검증.

**regrasp_to 기준** — `pickable: false` 자세를 어느 자세로 뒤집을지
- 가장 비슷한 `pickable: true` 자세 id 적기
- 모르면 `null` 유지

예시:
```yaml
- id: A
  pickable: true
  regrasp_to: null      # 직접 픽 가능
- id: C
  pickable: false       # 옆으로 누워있어 그리퍼 폭 초과
  regrasp_to: "A"       # 뒤집으면 A자세로 옴
```

### Step 6 — yaml 직접 수정 (선택)

위 4가지 정보를 yaml 파일에 직접 기록. 또는 메모지에 적어두고 캡처 후 한 번에 입력.

**yaml 직접 수정 시**: VSCode 또는 nano로 열어서 해당 부품 섹션의 null 값 채우기. **다른 필드 (transform_4x4 등) 건드리지 말 것**.

---

## 우선순위 (시간 부족 시)

5종 중 어느 부품을 먼저 검증할지:

| 순위 | 부품 | 이유 |
|---|---|---|
| 1 | **P5 main_body** | A·B 0.403 동일 = 대칭 의심 (가장 큰 라벨 리스크) |
| 2 | **⑤ plate_e** | 첫 캡처 대상 (SOP 우선순위 1번) — 검증 결과 즉시 활용 |
| 3 | **P3 bracket_sen_1** | 4/22 D435 매칭 실패 부품 — 자세 명세가 디버깅 단서 |
| 4 | **P2 cam_f_bracket** | top-3 72% = 자세 분류 가장 어려운 케이스 |
| 5 | **P1 guide_paper_cover** | 1pager 추정 "5+ 자세" 였으나 실제 4자세 — 검증 |

5/15 첫 30분 안에 1~3번 우선, 시간 남으면 4~5번. 못 한 부품은 5/15 저녁 또는 5/18 (월) 본 캡처 전에 추가.

---

## 검증 체크리스트

각 부품에 대해 yaml 의 다음 항목이 채워졌는가:

- [ ] 부품 레벨 `human_label` (외관 한 문장)
- [ ] 부품 레벨 `symmetry_groups` (대칭 있으면 그룹, 없으면 `null` 명시)
- [ ] 자세별 `human_label` (외관 한 문장)
- [ ] 자세별 `pickable` (true/false/null)
- [ ] 자세별 `regrasp_to` (pickable false면 대상 자세 id)
- [ ] 핸드폰 사진 (자세 id ↔ 외관 매핑 시각 기록)

---

## 5/15 본 캡처와의 연결

이 프로토콜 완료 후:

1. `auto_label.py` 가 `symmetry_groups` 를 자동 처리 → P5 A·B 라벨 통합
2. 첫 캡처 시 `find_closest_stable_pose` 가 정확한 자세 id 부여
3. ACCEPT 데이터의 `human_label` 이 사람-이해 가능 → REVIEW 큐 검수 시 외관 보고 빠르게 판정
4. `pickable: false` 자세 데이터는 별도 분류 → 학습 시 제외 또는 regrasp 학습 데이터로 활용

→ **이 30분이 5종 ~2,400장 데이터의 라벨 신뢰도를 결정합니다**.

---

## 트러블슈팅

| 증상 | 원인 | 대응 |
|---|---|---|
| 던지기 10회 결과가 yaml 확률과 크게 다름 | trimesh COM 추정 오차 (non-watertight STL 등) | yaml에 `human_observed_probability` 필드 추가 (5/15 후 코드 갱신) |
| yaml에 없는 자세가 자주 나옴 | threshold 0.05 잘림 | `pose_enumerator.py --threshold 0.02` 로 재생성 (자세 더 많이) |
| 자세 구별이 모호함 (외관 비슷) | 부품 자체가 대칭 또는 quasi-symmetric | `symmetry_groups` 에 묶기. 확신 없으면 빈 채로 |
| 부품이 한 자세로만 멈춤 (다른 자세 안 나옴) | 부품이 매우 안정적 (얇은 평면 등) | 의도적으로 다른 자세로 놓고 사진만 — 학습 데이터 부족 자세는 별도 라벨 |

---

## 관련 문서

- [학습 데이터 전략 1pager](binpicking_learning_data_strategy_1pager_20260511.md)
- [데이터 수집 SOP](binpicking_capture_sop_20260511.md)
- [pose_enumerator.py 코드](../bin_picking/src/recognition/pose_enumerator.py)
- [auto_label.py 코드](../bin_picking/src/labeling/auto_label.py) (대칭 그룹 처리: `canonicalize_pose_id`)
