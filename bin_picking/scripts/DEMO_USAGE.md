# 라이브 인식 데모 사용 가이드

**스크립트**: `bin_picking/scripts/demo_live_recognition.py`
**UI 모듈**: `bin_picking/src/visualization/demo_ui.py`

## 용도

Basler 2대(Blaze-112 ToF + ace2 RGB) 입고 후 대표님께 실시간 인식을 시연하기 위한 도구.
카메라 도착 전에는 D435 / 저장 프레임 / 합성 씬으로 리허설 가능.

## 화면 구성 (2×2 그리드, 1296×1048px)

```
┌──────────────────────┬──────────────────────┐
│  ① ace2 RGB          │  ② Blaze-112 depth   │
│  (원본 또는 리사이즈)│  (viridis 컬러맵)    │
├──────────────────────┼──────────────────────┤
│  ③ 인식 결과 오버레이│  ④ 성능/매칭 표      │
│  (depth + bbox 투영) │  (ACCEPT/WARN/REJECT)│
└──────────────────────┴──────────────────────┘
```

## 4가지 동작 모드

### A. Basler 라이브 (본 데모, 4/23 이후)
```bash
sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --basler
```
- Blaze-112 + ace2 실시간 스트림
- 부품을 카메라 앞에 놓고 `c` 키로 캡처

### B. RealSense D435 라이브 (리허설용)
```bash
sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --realsense
```
- Basler 오기 전 검증에 유용
- D435 USB 케이블 제약 있으니 세팅 유의

### C. 저장된 프레임 (오프라인)
```bash
.venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py \
    --load ~/Desktop/d435_bracket_retry2
```
- 이미 촬영한 프레임 재생 → `c` 키로 파이프라인 재실행
- 회의 자료 만들 때 편함

### D. 합성 씬 (완전 오프라인)
```bash
.venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --synthetic
```
- 카메라 없이 UI 레이아웃만 확인
- 박스 3개 흔들리는 가짜 씬

## 키보드 조작

| 키 | 동작 |
|----|------|
| `c` 또는 `SPACE` | 현재 프레임 캡처 → L1~L5 파이프라인 → 결과 오버레이 |
| `s` | 현재 화면을 PNG로 저장 (`/tmp/demo_YYYYMMDD_HHMMSS.png`) |
| `r` | 결과 리셋 (라이브 모드 복귀) |
| `q` 또는 `ESC` | 종료 |

## 레진 프리셋 (선택)

파이프라인 파라미터를 레진 종류에 맞춰 전환:

```bash
# Clear 레진 (반투명 → voxel 3mm, SOR 엄격, multiscale ON)
--resin clear

# Flexible 레진 (Huber kernel, ICP 거리 1.5배)
--resin flexible

# Grey/White (표준, 기본값과 동일)
--resin grey
```

## 디스플레이 없는 환경 (CI/검증)

GUI 없이 1회 렌더링만 PNG로 저장:

```bash
python bin_picking/scripts/demo_live_recognition.py \
    --synthetic --test-render /tmp/demo_test.png
```

서버/CI에서 UI 정상 렌더링 여부만 확인할 때 사용.

## 권장 시연 순서 (대표님 시연)

1. **카메라 연결 + 스트림 확인**
   ```bash
   sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --basler
   ```
2. **라이브 상태 시각** — ①②가 실시간으로 업데이트되는 것 먼저 보여드림
3. **부품 올리기** — 검은 배경 위에 실물 부품 1개
4. **캡처** — `c` 키 → 1~2초 내 ③④ 업데이트
5. **결과 해석** — 부품명, fitness, RMSE, 판정 설명
6. **다른 부품** — 리셋(`r`) 후 다른 부품 올리기
7. **화면 저장** — `s` 키로 중요 순간 PNG 확보

## 실행 전 준비물

- venv 활성화: `source .venv/binpick/bin/activate`
- 검은 배경 (천/마우스패드)
- 카메라 고정대 (USB 짧을 경우 주의)
- CAD 레퍼런스 캐시 빌드된 상태 (`cad_library.py --build` 이미 실행됨)

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| `pypylon` ImportError | venv 미활성화 | `source .venv/binpick/bin/activate` |
| depth 유효 픽셀 0% | 카메라 거리 / 조명 | 300~1500mm 범위 확인 |
| 모든 클러스터 REJECT | CAD 등록되지 않은 물체 | 정상 (미등록 물체는 거부하는 게 의도) |
| 파이프라인 10초+ | 후보 수 너무 많음 | `--resin` 또는 SizeFilter 정상 동작 확인 |
| 창이 안 뜸 (macOS) | OpenCV 권한 | `sudo` 실행 또는 환경 점검 |

## 참고 자료

- [demo_ui.py](../src/visualization/demo_ui.py) — UI 렌더러 모듈
- [main_pipeline.py](../src/main_pipeline.py) — 파이프라인 본체
- [resin_presets.py](../config/resin_presets.py) — 레진별 파라미터 SSOT
