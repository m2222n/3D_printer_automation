# 빈피킹 데이터 수집 SOP (Standard Operating Procedure)

**작성**: 2026-05-11
**적용 시점**: 어댑터(ipTIME U1G-C) 도착 + Basler 라이브 검증 완료 후 (예: 5/15 금요일~)
**전제**: `test_basler_live.py --discover` PASS + Blaze depth + ace2 RGB 라이브 OK

> **목적**: 부품 1종 ~500장 학습 데이터를 일관된 품질로 수집.
> 어댑터 도착 후 매뉴얼대로 따라하면 1종당 1~2시간 안에 데이터셋 완성.
>
> **참고 문서**:
> - 학습 데이터 전략 (이 SOP의 상위): `docs/binpicking_learning_data_strategy_1pager_20260511.md`
> - 안정 자세 yaml: `bin_picking/config/stable_poses.yaml`
> - 어댑터 검증: `memory/project_basler_office_setup_0508.md` § 어댑터 도착 후 검증/셋업 절차

---

## 1. 셋업 (1회만, 30분)

### 1.1 카메라 마운트

```
        [Basler Blaze-112 + ace2 통합 브라켓]
                        ↓
                  카메라 60~80cm
                        ↓
                  [회전대]
                        ↓
                  [부품 1개]
                        ↓
                  [평평한 배경판]
```

**카메라 거리 선택 근거**:
- Blaze 작동거리: 300~3000mm
- 최적 거리: 500~1500mm (depth 정밀도 + FOV 균형)
- **권장 60~80cm** (실제 빈피킹 환경 = 빈 위 60~80cm와 유사)
- 너무 가까우면 (< 40cm): depth 양자화 (4/22 D435 USB 20cm 케이스와 유사 위험)
- 너무 멀면 (> 1.5m): FOV 안에 부품 너무 작아짐

**Blaze + ace2 브라켓**:
- 5/6 회의 결정: 코에버 설계 → 오리누 3D 출력 → 검증 후 철제
- **현재 브라켓 설계 미수령** → 임시로 두 카메라 따로 마운트 또는 평행 고정 (eye-in-hand 캘리브는 추후)

**고정 방법**:
- 모니터 위 / 책장 위 / 카메라 삼각대 / 책 쌓기 등
- **반드시 단단히 고정** (촬영 중 흔들리면 데이터 무효)
- 카메라 광축이 회전대 중심을 향하도록

### 1.2 회전대 (선택, 필수 아님)

> ⚠️ **재평가 (5/11)**: 회전대는 편의용이지 필수가 아니다.
> 자동 라벨링(`auto_label.py`)이 yaw를 알고리즘으로 산출하므로,
> `meta.json`의 사람 측정 yaw는 참고용. 학습 라벨은 L4 매칭 결과(T_world)임.

#### 옵션 A: 회전대 없이 (즉시 가능, 0원)

**방법**: 부품을 책상 위에 놓고 자세 + 각도 손으로 다양하게 변경

```
자세 A로 5~10장 (yaw 대충 다양하게)
자세 B로 5~10장
자세 C로 5~10장
조명 변형 (자세 A 유지하고 책상 등만 켜기) 5장
배경 변형 (자세 A 유지하고 다른 배경) 5장
```

→ 자세 1개당 30~50장. 1종당 100~200장으로 충분.

**장점**:
- 즉시 시작 가능
- 회전대 사러 가는 시간 절약

**단점**:
- yaw 0/15/30/...같은 정확한 간격 어려움 → 그래도 학습엔 OK

#### 옵션 B: 다이소 회전 받침대 (편의, 5,000~10,000원)

본격 양산 단계 (예: 5종 × 500장 = 2,500장) 시 매번 손으로 두는 게 피곤해지면 구매.
지금 단계 (prototype + 5종 검증)는 옵션 A로 충분.

- 키워드: "케이크 회전판" / "수동 회전 받침대"
- 지름 20~30cm
- A4 각도 디스크 부착 (선택)

#### (백업) 전동 턴테이블

본격 양산 단계 (29종 × 1000장+) 시 검토. 현재는 불필요.

### 1.3 조명

**기본 3가지 변형** (부품 1종당 모두 촬영):

| 라벨 | 광원 | 설명 |
|------|------|------|
| `normal` | 천장 + 책상 등 (기본 조명) | 표준 |
| `low` | 책상 등만 (조도 50% 낮춤) | 그늘 케이스 |
| `side` | 한쪽 측면 강조 (스마트폰 손전등 등) | 그림자 강조 |

→ Layer 2 데이터셋 다양성 확보. 학습 모델 강건화.

### 1.4 배경

**기본 3가지 변형**:

| 라벨 | 배경 | 설명 |
|------|------|------|
| `white` | 흰색 A4 | 표준 (높은 대비) |
| `dark` | 검정/회색 천 | 낮은 대비 |
| `mixed` | 부품 일부 가려짐 (다른 부품 옆에) | 부분 가시 (occlusion) |

⚠️ `mixed`는 후처리 시 단일 부품 가정 깨질 수 있음 → 별도 폴더 / `auto_label.py` 단독 모드 OFF

---

## 2. 수집 절차 (부품 1종당, 1~2시간)

> 💡 **권한 주의 (5/11 정정)**: Basler GigE Vision = 이더넷 통신. macOS USB raw access 제약 없음.
> **sudo 없이 실행**. RealSense D435(USB)의 sudo 패턴 (4/13 메모리)을 Basler에 적용하면 안 됨.
> 권한 에러 발생 시에만 추가 검토 (드물게 pypylon 설치 권한 문제 시).

> 🔧 **macOS Blaze 운영 (5/12 검증)**:
> - Blaze Supplementary macOS 미지원 → pypylon 단독으로 작동 가능 (검증 완료, commit 7e28df9)
> - EnumerateDevices() Blaze 미발견 → **IP 직접 fallback 필수**:
>   ```bash
>   export BASLER_BLAZE_IP=192.168.20.10   # ⭐ Mac에서 필수
>   # 또는 BaslerCapture(blaze_ip="192.168.20.10") 인자
>   ```
> - 네트워크: Mac en8 (192.168.20.1/24, ipTIME U1G-C) ↔ Blaze (192.168.20.10/24, Static)
>   - 192.168.20/24 = 사무실 Wi-Fi (192.168.10/24)와 영구 분리 → Wi-Fi 켠 채 작업 가능
> - Blaze 실 해상도: **848×480** (매뉴얼 640 가정 오류, 5/12 실측)

### 2.1 사전 준비 (5분)

```bash
# 1. 환경 활성화
cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation   # Mac 작업 경로
source .venv/binpick/bin/activate

# 2. Blaze IP 환경변수 (macOS 필수, EnumerateDevices fallback)
export BASLER_BLAZE_IP=192.168.20.10
# (선택) ace2 IP — 한솔에서 부품 인수 + IP 할당 후
# export BASLER_ACE2_IP=192.168.20.11

# 3. 카메라 인식 확인 — sudo 불필요 (Basler GigE)
python bin_picking/tests/test_basler_live.py --discover
# → Blaze 발견 확인 (ace2는 아직 한솔 보유 중이라 --no-ace2 사용)

# 2. 캡처 저장 디렉토리 준비
PART="plate_e"      # 부품 ID (stable_poses.yaml 키와 일치)
POSE="A"            # 안정 자세 ID (stable_poses.yaml 참조)
LIGHT="normal"      # 조명 라벨
BG="white"          # 배경 라벨
DATE=$(date +%Y%m%d)

CAPTURE_DIR="bin_picking/models/captures/${DATE}_${PART}_pose${POSE}_${LIGHT}_${BG}"
mkdir -p "$CAPTURE_DIR"

# 3. 부품을 자세 A로 회전대에 놓고 → 카메라 광축 중심에 오도록 조정
```

**5/12 검증된 실행 예시** (사무실 천장/벽, 부품 미배치, --no-ace2):
```bash
BASLER_BLAZE_IP=192.168.20.10 python bin_picking/tests/test_basler_live.py \
  --live --save --no-ace2

# 기대 출력:
# - Warmup 10/10 PASS
# - shape (480, 848) uint16, 유효 픽셀 % 50~90 (부품 거리/시야 의존)
# - depth 범위 (mm), 중앙값, unique 값 > 300 (양자화 OK)
# - 캡처 시간 ~0.05s, 저장 ~800KB, 라운드트립 PASS
```

### 2.2 yaw sweep 촬영 (15° × 24 = 360°, 30분)

```bash
# 0°부터 시작
i=0
for yaw in 0 15 30 45 60 75 90 105 120 135 150 165 180 195 210 225 240 255 270 285 300 315 330 345; do
  printf -v frame "frame_%04d" $i

  echo "회전: yaw=${yaw}° (frame ${frame})"
  echo "→ 회전대를 ${yaw}°에 맞추세요 (디스크 눈금 확인)"
  echo "→ 부품이 흔들리지 않는지 확인"
  read -p "Enter 누르면 캡처: "

  .venv/binpick/bin/python bin_picking/tests/test_basler_live.py \
    --live --save \
    --output "${CAPTURE_DIR}/${frame}"

  # meta.json에 yaw 추가 정보 추기 (수동 또는 sed)
  python3 -c "
import json
from pathlib import Path
meta_path = Path('${CAPTURE_DIR}/${frame}/meta.json')
meta = json.loads(meta_path.read_text())
meta.update({
  'part_id': '${PART}',
  'stable_pose_id': '${POSE}',
  'yaw_deg': ${yaw},
  'pitch_deg': 0,
  'light': '${LIGHT}',
  'background': '${BG}',
})
meta_path.write_text(json.dumps(meta, indent=2))
"

  i=$((i+1))
done
```

⚠️ **첫 2~3장만 찍어보고 결과 확인 후 본 수집** — 조명/거리/포커스 검증

### 2.3 pitch 변형 촬영 (선택, 30분)

부품이 안정 자세 외 자세도 가능하다면:
- 회전대 자체를 살짝 기울이기 (15° 틸트) 또는
- 부품 아래 작은 받침 (5mm) 끼우기
- 동일 yaw sweep 반복

→ Layer 2 § 다각도 촬영의 pitch sweep 구현

### 2.4 조명/배경 변형 (1시간)

조명 변형:
```bash
# normal → low (책상 등만) → side (측면 강조)
# 각 변형마다 yaw 12개 (30° 간격, 빠른 sweep)
```

배경 변형:
```bash
# white → dark → mixed
# 각 변형마다 yaw 12개
```

→ 합계: 자세 1개당 ~120장 (24 yaw + 12×2 pitch + 12×3 light + 12×3 bg ≈ 100~150)

### 2.5 자세 A → 자세 B → C 반복

`stable_poses.yaml`의 자세 N개에 대해 반복.
- plate_e: 3자세 (A 250장, B 150장, C 100장 = 500장)
- bracket_case: 4자세
- main_body: 4자세 (A·B 대칭 → 통합 가능)
- cam_f_bracket: 5자세
- guide_paper_cover: 4자세

총 5종 ~2,400장 (1pager § 5)

---

## 3. 자동 라벨링 (수집 후, 10분)

```bash
# 부품/자세별로 한 번에
.venv/binpick/bin/python bin_picking/src/labeling/auto_label.py \
  --capture-dir "${CAPTURE_DIR}" \
  --part "${PART}" \
  --camera "blaze-112" \
  --output "bin_picking/models/dataset_v1/" \
  --stable-poses "bin_picking/config/stable_poses.yaml"

# 결과 확인
# - ACCEPT 비율 (목표 ≥ 80%)
# - REVIEW 사유 분포
# - 자세 분포 (yaml의 stable_pose_id와 일치하는지)
```

**품질 게이트** (`auto_label.py` 기본값):
- RMSE < 1.5mm
- fitness > 0.3
- cluster 200~50,000 points
- pose match score > 0.85 (회전 18° 이내)

→ ACCEPT 미달이면 게이트 완화 vs 셋업 점검 결정

---

## 4. 품질 체크리스트

수집 중간/완료 후 확인:

### 4.1 캡처 품질
- [ ] depth 유효 픽셀 비율 > 70% (`test_basler_live.py` 통계)
- [ ] depth 유니크 값 > 30 (4/22 D435 케이스 재현 X)
- [ ] color 노출 적정 (너무 어둡거나 밝지 않음)
- [ ] 카메라 흔들림 없음 (yaw=0 ↔ yaw=360 거의 동일해야)

### 4.2 라벨링 품질
- [ ] ACCEPT 비율 ≥ 80%
- [ ] 한 자세 내 yaw 변화에도 stable_pose_id 일관 (예: pose A에서 24장 다 sp_id=A)
- [ ] RMSE 중앙값 < 1.0mm
- [ ] pose_match_score 중앙값 > 0.95

### 4.3 데이터셋 다양성
- [ ] 각 자세별 ≥ 100장
- [ ] 조명 3종 / 배경 3종 골고루 분포
- [ ] yaw 0~360 균일 분포

---

## 5. 트러블슈팅

| 증상 | 원인 | 대응 |
|------|------|------|
| `test_basler_live.py --discover` 0개 | 어댑터 / IP / 전원 | 5단계 진단 (`memory/project_basler_office_setup_0508.md`) |
| depth 유효 픽셀 < 50% | 거리/반사 | 거리 조정 (60~80cm 권장), SLA 광택 표면은 무광 페인트 |
| depth 유니크 값 < 20 | 양자화 (4/22 케이스) | 거리 늘리기, FOV에 부품 더 크게 |
| ACCEPT 비율 < 50% | 셋업 또는 CAD 불일치 | (a) 셋업 점검 / (b) CAD 캐시 재빌드 / (c) `--part` 지정해서 매칭 좁히기 |
| pose_id가 자세별로 안 맞음 | stable_poses.yaml 회전 매핑 | yaml 재생성 (`pose_enumerator.py`) 또는 수동 보정 |
| 한 yaw에서 cluster 0개 | 부품이 카메라 시야 밖 | 부품 위치 조정, ROI 확장 |
| 시간 너무 오래 걸림 | yaw 24개 × 자세 N × 조명 3 × 배경 3 | 차원 축소 (조명만 normal로, 배경만 white로) |
| **macOS** `--discover` 0개 (5/12 워크어라운드) | EnumerateDevices Blaze 미동작 | `BASLER_BLAZE_IP=192.168.20.10` 환경변수 export 후 재실행. IP fallback으로 우회 |
| **macOS** "Coord3D_C16 사용 불가" / "Blaze Supplementary 필요" | macOS Blaze SDK 미지원 | basler_capture.py가 자동 처리 (Range component + Mono16 raw로 동일 mm depth). 별도 조치 불필요 |
| ping 192.168.10.x 시 카메라 통신 안 됨 | Wi-Fi (192.168.10/24)와 어댑터 IP 충돌 | 어댑터+카메라를 **192.168.20/24**로 이동 (`memory/project_basler_office_setup_0508.md` § 5/12 영구 분리 참조) |
| Blaze 해상도 (480, 640) 기대했는데 (480, 848) | 매뉴얼 가정 오류 | **848×480이 native 해상도** (5/12 실측). 코드는 정상 (`BLAZE_112_SPEC.width=848`). meta.json에 width 848로 저장됨 |

---

## 6. 시간 예산 (1종당)

| 단계 | 시간 |
|------|------|
| 사전 준비 (셋업) | 5분 |
| yaw sweep × 자세 N | 자세당 30분 (24장 + 메타 입력) |
| 조명 변형 (12장 × 3) | 30분 |
| 배경 변형 (12장 × 3) | 30분 |
| 자동 라벨링 | 10분 |
| 결과 확인 | 10분 |
| **합계** | **자세당 ~80분 + 변형 ~70분 = 150분 (~2시간)** |

5종 × 평균 3자세 × 2시간 = **약 30시간** (1주일 풀타임)

→ KAIST 화/목 빼고 월/수/금 = 3일에 5종 가능. 욕심 부리지 말고 자세 우선순위 (1pager § 5 표).

---

## 7. 우선순위 (실제 수집 순서)

| 순위 | 부품 | 이유 |
|------|------|------|
| 1 | **plate_e** | 가장 단순 (3자세, 평면 부품). SOP 검증용 |
| 2 | **bracket_case** | 박스형, 안쪽 슬롯 = 그래스프 검증 |
| 3 | **main_body** | 대칭 부품 → 라벨링 통합 케이스 |
| 4 | **cam_f_bracket** | 소형, SizeFilter 검증 |
| 5 | **guide_paper_cover** | 가장 복잡 (4자세), 학습 한계 검증 |

→ 1번부터 진행하며 SOP 자체를 다듬기. 5번까지 가면 데이터셋 v1 완성.

---

## 8. 이력

- v1 (2026-05-11): 초안 작성. 어댑터 도착 전 예측 기반. 실 촬영 시 실측 반영해 v2 작성 예정.

---

## 9. 관련 코드

| 파일 | 역할 |
|------|------|
| `bin_picking/tests/test_basler_live.py` | 카메라 캡처 (--live --save) |
| `bin_picking/src/recognition/pose_enumerator.py` | 안정 자세 yaml 생성 |
| `bin_picking/src/labeling/auto_label.py` | 자동 라벨링 + 데이터셋 구조 |
| `bin_picking/src/acquisition/basler_capture.py` | Basler 캡처 API |

## 10. 관련 메모리

- `project_binpicking_predev_codes_0511.md` — 사전 디벨롭 코드 작업 (이 SOP의 인프라)
- `project_basler_office_setup_0508.md` — 어댑터 검증 8단계
- `project_realsense_d435.md` — 4/22 USB 20cm 양자화 케이스 (재현 방지 학습)
- `reference_basler_blaze_112.md` — 카메라 하드웨어 사양
