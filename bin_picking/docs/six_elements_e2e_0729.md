# 6요소 좌표 E2E 완주 (depth_track → 협력사 규격, 2026-07-29)

> **P0 #2** 완료. depth_track 추론 → 협력사 6요소(`x, y, z, edge, angle, label`) 변환을
> 실측 100장에서 검증. **z 유효 801/801건(100%), 99%가 400~600mm 정상 범위.**
> 신설 = `bin_picking/src/pipeline/depth_track_to_6elements.py`

## 왜 새 모듈이 필요했나

기존 `yolo_track/pipeline/detect_and_output.py`는 **YOLO(RGB) 전용**이라 그대로 쓸 수 없다:

| | yolo_track | depth_track |
|---|---|---|
| 입력 | RGB 이미지 + YOLO 모델 | **depth 1장** + DETR계열 예측 JSON |
| 좌표계 | 원본 프레임 | ⚠️ **crop·resize된 입력 프레임** |
| 라벨 | `Part1~5` | `cad_id`(예: `18_button_function_niro__d790553b`) |
| depth 단위 | mm 가정 | ⚠️ **uint16 (mm 아님)** |

## 🐛 잡은 버그 2건 — 둘 다 "조용히 틀리는" 종류

### ① uint16 스케일 오해 → z가 6~7배 과대

첫 출력에서 z가 **3136~3358mm**로 나왔다. 부품 촬영 실거리(450~500mm)와 6~7배 차이.

- **원인**: 실측 npy가 uint16이지만 **mm가 아니다**. 올바른 변환은
  `depth_m = raw × (10.0 / 65535)` — 근거 `eval_real_depth_vq_detector.py:135`,
  `depth_preprocess.py:54`. raw를 mm로 그대로 median 했다.
- **검산**: raw 3212 × 10/65535 = **0.490 m = 490 mm** ✅
- ⭐ **잡아낸 단서 = "400~600mm 픽셀이 0개"**. eval이 `--depth_keep_range 0.40,0.60`으로
  부품 대역만 남기는데, 내 출력엔 그 대역이 아예 없었다.
  **값이 그럴싸해 보여도(3.2m는 실내 거리로 자연스럽다) 물리 검산을 해야 한다.**

### ② 중심 5×5 구멍으로 z 실패 114건(14.2%)

- **원인**: Blaze ToF가 부품 경계·반사면에 구멍을 낸다. 장면 전체 유효 depth가 **3%까지
  떨어지는 프레임**도 있다(`shot_040_g2`). 중심 window 5가 하필 구멍에 걸린다.
- **관찰**: 실패 건도 **bbox 안에는 depth가 9~37% 남아 있었고**, win31로 넓히면
  전부 **483~500mm**로 정상 복구됐다 → 버릴 데이터가 아니었다.
- **처방**: `_bbox_median_depth()` fallback 추가 → **z 유효 100%**.
  ⚠️ bbox median은 배경을 섞을 위험이 있어 `notes`에 출처를 남긴다
  (`bbox_median_fallback_valid=N(x%)`). 로봇이 z를 쓰기 전에 확인 가능.

## 좌표 역변환 (이 모듈의 핵심)

```
원본 depth 848×480
  └ center_crop 1/6~5/6 → crop_bbox_yxyx [80,141,400,707]  (320×566)
      └ resize          → input_shape_hw [320,576]   ← 예측 bbox가 이 좌표계
```

6요소 규격이 **원본 기준**(`image_shape: [480, 848]`)이므로 **resize 역스케일 → crop 오프셋 가산**이 필요하다.

**단위 테스트로 검증**:
| 검증 | 결과 |
|---|---|
| 입력 (0,0) → 원본 | (141, 80) = crop 시작 ✅ |
| 입력 (576,320) → 원본 | (707, 400) = crop 끝 ✅ |
| 입력 576×320 → 원본 크기 | 566×320 (x축만 축소 = 크롭이 566폭) ✅ |

⚠️ 이 역변환을 빼먹으면 좌표가 **(141, 80)만큼 밀리고 스케일도 어긋난다**.

## 결과 (실측 100장)

| 항목 | 값 |
|---|---|
| 장면 / 검출 | 100 / **801건** |
| **z 유효** | **801 (100%)** — center_median 687 + bbox_fallback 114 |
| z 범위 | 391 ~ 586 mm (중앙 **461**) |
| 400~600mm 내 | **99.0%** (미달 7건 = <400mm) |

**단일 장면 예시** (`shot_009_g1`, 9건): z 478~512mm(중앙 493), 편차 34mm
= 부품 두께·적재 높이차로 타당. `camera_3d` Xc/Yc가 ±175mm 이내 = 빈 크기와 정합.

⭐ **intrinsics는 7/28 실측값을 자동 로드**(`fx=309.3 fy=310.1 ppx=410.1 ppy=249.3`).
추정값 하드코딩 금지 — 7/28에 `fy=188`(65% 오류)이 정렬 실패의 진짜 원인이었다.
⚠️ 참고로 `sample_output_6elements.yaml`의 intrinsics는 **옛 추정값**(`fx=fy=553`)이라
그 파일은 형식 참고용으로만 볼 것.

## ⚠️ 한계 (로봇 연동 전 반드시 알아야 할 것)

1. **`angle = 0.0` 고정, `edge` = 축정렬 bbox 4코너** — 예측 JSON에 **마스크 픽셀이
   저장되지 않는다**(`mask_area`만). 진짜 contour·회전각이 필요하면 eval에서 마스크를
   저장하도록 고쳐야 한다(별건). 현재는 `detect_and_output.py`의 v2(detection) 단계와 같은 한계.
   🚨 **회전 대칭이 아닌 부품은 angle 없이 파지 자세를 정할 수 없다** → 실피킹 전 해소 필요.
2. **좌표계 = Blaze 카메라 프레임** — 로봇 Base 변환(**hand-eye 캘리브**)은 **미착수**.
   로봇이 있어야 구한다(재택 불가).
3. **z는 bbox 중심 1점** — 부품 표면의 파지점 z가 아니다. `grasp_database.yaml`의
   `grasp_depth_mm`·`approach_axis`와 결합해야 실제 접근 좌표가 된다.
4. **평가 데이터가 학습에 섞였다** → [[binpicking-gap-analysis-0728]] §리스크1.
   이 100장은 좌표 **형식·스케일 검증**용이며 인식 성능 근거로 쓸 수 없다.

## 사용

```bash
V=/data/jtm/depth_venv/bin/python
# 1건
$V bin_picking/src/pipeline/depth_track_to_6elements.py \
    --pred <예측>.json --out <출력>.json
# 디렉토리 일괄
$V bin_picking/src/pipeline/depth_track_to_6elements.py \
    --pred-dir /data/jtm/synth_out/eval_cpu_0729_full100/predictions \
    --out-dir /data/jtm/synth_out/6elements_100
```

산출물: `/data/jtm/synth_out/6elements_100/` (100건), `6elem_shot_009_g1.json` (단일 예시)

## ⏭️ 다음

1. **Modbus 시뮬레이터로 핸드셰이크 검증** — 실물 로봇 없이 통신 로직 완성 가능
   (`pymodbus` 보유, 레지스터 130~135·150/151·200/206 + 8단계 → [[reference-hcr-manuals-0727]])
2. 🔴 **마스크 저장 → angle 산출** — 회전 비대칭 부품 파지의 전제
3. ⏸️ **hand-eye 캘리브** — 로봇 필수
