# `synth/` — 디지털 트윈 합성데이터 파이프라인

CAD(STL) 27부품을 가상 빈(bin)에 **중력으로 낙하·적재**시켜 장면을 만들고, **Depth / Segmentation / 6DoF pose 라벨을 자동 생성**한다. 실물 카메라·수동 라벨링 없이 코드만으로 라벨링된 학습 데이터를 만드는 것이 핵심이다.

- **도구**: [BlenderProc](https://github.com/DLR-RM/BlenderProc) (Blender 4.2 물리엔진 + 멀티모달 렌더)
- **부품 색**: 회색 단색 고정 — 색이 다양하면 모델이 형태가 아니라 색으로 판별할 위험이 있어, depth·형상만으로 구분하도록 통일.
- **배경**: 부품 픽셀만 남기고 나머지는 NaN (2D 인코더 학습셋 기준).

## 실행 원칙 — 1 scene = 1 프로세스

각 scene을 **독립 프로세스**로 생성한다(`gen_one*.py` 한 번 = 한 장면). BlenderProc은 프로세스 내 상태가 누적되면 장면 간 오염이 생길 수 있어, scene마다 새 프로세스로 띄우고 배치 러너(`run_*.sh`)가 인덱스를 병렬 분배한다. 러너는 **resume**를 지원한다(이미 있는 `scene_*.npz`는 건너뜀).

```bash
# 예: 2D 인코더 학습셋 1,000장 생성 (6워커)
bash run_camnear_batch.sh 1000 6
```

## 장면당 자동 출력 (수동 라벨링 0)

| 산출 | 내용 |
|------|------|
| `depth` | (512×512) float32, 배경 NaN (또는 0-1 정규화본에선 배경 0) |
| `inst_id` | 인스턴스 세그맵 (부품 1..n, 배경 0) |
| `category_id` | 클래스 세그맵 (부품 1..27, 배경 0) |
| `meta` | 부품별 6DoF 자세(quaternion + euler), 카메라 높이(cam_h) 등 |

- **scene 전체 npz** + **부품별 crop npz** 둘 다 저장.
- scene 단위 800 / 100 / 100 (train/val/test)로 split — crop(부품) 단위로 쪼개면 같은 장면 부품이 train/test에 섞여 정보 누수가 생기므로 장면 단위로 분할한다.

## 데이터셋 버전 히스토리

| 버전 | 생성기 | 부품 | 배경 | 의도 |
|------|--------|------|------|------|
| v1 | `gen_one.py` | 회색 단색 | 단색 | 기본 형상 |
| v2 | `gen_one_v2.py` | 색·텍스처 랜덤 | 도메인 랜덤화 | 실제 배경 미확정 대응 |
| v3 | `gen_one_v3.py` | 회색 단색 고정 | 2종(적재형/정렬형) | 형태로 판별 + 빈피킹 2시나리오 |
| 2D 인코더 학습셋 | `gen_one_2denc.py` | 회색 단색 | 배경 NaN | 현재 모델 학습용 1,000 scene |
| cam_sweep | `gen_one_2denc_camsweep.py` | 회색 단색 | 배경 NaN | 카메라 거리 스윕(0.4~1.0m)으로 원근 프로파일 다양화 |
| **cam_near** | **`gen_one_2denc_camnear.py`** | **회색 단색** | **배경 NaN** | **실측 실거리(45~50cm)에 정합한 카메라 높이(0.43~0.57m)** |

## 스케일 정합 (sim2real)

합성으로 학습한 모델을 실물로 채점할 때, 검출·분할(위치)은 유지되나 식별이 무너지는 원인이 **합성↔실측의 카메라↔부품 거리(원근 프로파일) 불일치**였다. 실측 촬영 거리(약 45~50cm)에 맞춰 카메라 높이를 정합하면 식별이 크게 회복된다.

- 절대 depth 값은 모델 입력단의 robust 정규화(median-subtract, p95−p05)가 흡수하므로, 관건은 값이 아니라 **부품이 화면에 찍히는 크기·원근**이다.
- `normalize_synth_01.py` 는 합성 depth를 실측과 **동일한 per-scene 0-1 정규화**로 통일해 train/test 전처리를 일치시킨다.

## 파일 안내

### 장면 생성기 (`gen_one*.py`)

| 파일 | 역할 |
|------|------|
| `gen_one.py` / `gen_one_v2.py` / `gen_one_v3.py` | 데이터셋 버전별 1 scene 생성기 |
| `gen_one_2denc.py` | 2D 인코더 학습용 생성기 (depth + 인스턴스 마스크 + class + 6DoF 자세 메타) |
| `gen_one_2denc_camsweep.py` | 카메라 거리 스윕(0.4~1.0m), FOV 고정 |
| `gen_one_2denc_camnear.py` | **실측 실거리 정합(cam_h 0.43~0.57m)** |
| `gen_one_2denc_camsweep_hi.py` | 원거리 스윕(0.5~1.6m) — 실험 보관용 |

### 후처리·유틸

| 파일 | 역할 |
|------|------|
| `normalize_synth_01.py` | 합성 depth → 부품 per-scene 0-1 정규화 (실측과 전처리 통일) |
| `depth_noise.py` | ToF depth 노이즈 모델 (거리비례 Gaussian + dropout + flying pixel) |
| `probe_3d_coords.py` / `probe_3d_coords_normalized.py` | CAD에서 3D 좌표(키포인트·주축·grasp 등) 추출 |
| `extract_all.py` / `extract_preview.py` / `run_png_export.sh` | 렌더 결과 → PNG 추출 (육안 검증·시연용) |
| `make_meeting_figs.py` | 발표·미팅용 비교 figure 생성 |
| `poc_gravity_drop.py` | 중력 적재 물리 PoC |

### 배치 러너 (`run_*.sh`)

각 데이터셋 버전에 대응하는 병렬 생성 러너. 공통적으로 `run_<name>.sh <총장수> <워커수>` 형태이며 resume를 지원한다.

> ⚠️ 데이터셋(npz/npy/png)·CAD(STL)는 용량 문제로 git에 포함하지 않는다(`.gitignore` 참고). 생성 스크립트만 추적한다.
