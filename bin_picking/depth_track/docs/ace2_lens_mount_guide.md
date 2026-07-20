# ACE2 RGB 렌즈 장착·검증 가이드 (현장 작업)

> 목적: RGB 융합의 **맨 앞 블로커** = ace2에 렌즈 달아 "형상이 잡히는지" 확인.
> 6/15 렌즈 입고(8mm+12mm) 후 첫 장착. 5/20엔 렌즈 없어 형상 못 잡았음(핀홀 상태).
> ⚠️ **실물 카메라 작업 = Mac에서 태민님이 직접**. 6000(원격)에선 pypylon·cv2 없어 불가.

## 준비 (Mac)
- ace2 본체 + 렌즈 2종(8mm C23-0824-5M / 12mm C23-1224-5M)
- ipTIME U1G-C 어댑터 + LAN, ace2 전원(12V LOADUS EQ-4212Fctc)
- Mac 네트워크: en(어댑터) = `192.168.20.1/24`, ace2 = `192.168.20.20/24`
- 코드 환경: `cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation && source .venv/binpick/bin/activate` (venv, pypylon 26.4.1)

## 순서

### 1) 렌즈 장착 — 먼저 8mm (빈피킹 유력)
- ace2 정면 C-mount 캡 제거 → **8mm 렌즈를 시계방향 끝까지** 돌려 장착
- 조리개(iris)·포커스 링이 자유롭게 도는지 확인 (Premium 아니라 잠금나사 없음)

### 2) 라이브뷰 실행 + 포커스 맞추기
```bash
export BASLER_ACE2_IP=192.168.20.20
python bin_picking/tests/live_viewer_ace2.py --packet-size 1500
```
- ⚠️ **grab 실패('incompletely grabbed' / drop 다발)면 throughput 낮추기**:
  ```bash
  python bin_picking/tests/live_viewer_ace2.py --throughput 20   # 안 되면 15 → 10
  ```
  7/20 Blaze가 macOS Tahoe + USB이더넷 어댑터에서 buffer underrun으로 grab 전량
  실패했던 것과 동일 원인. ACE2는 5MP(6.5MB/frame)라 Blaze(depth 848×480)보다
  무거워 더 낮은 값이 필요할 수 있음. 기본 30Mbps → drop 뜨면 순차 하향.
  포커스 맞추는 정지 작업이라 낮은 fps여도 무방.
- 화면 뜨면 `f` 눌러 **FOCUS score 표시 ON**
- 카메라 앞 30~50cm에 글자·패턴 있는 물체(자·부품·인쇄물) 놓기
- **포커스 링을 천천히 돌리며 score 최대화**:
  - `FOCUS score > 100` (초록) = 선명 ✅ **성공 기준**
  - `> 30` (노랑) = 그럭저럭
  - `< 30` (빨강) = 흐림 (더 조정)
- 조리개가 너무 조여 어두우면 iris 열기, 화면 하얗게 뜨면 `[`로 노출 낮추기(또는 `a` 자동노출)

### 3) 판정 = 5/20 대비 결정적 차이
- ✅ **성공**: 물체 **형상·윤곽이 또렷**하게 보이고 score 100+ → **렌즈 정상, RGB 카메라 살아있음**
  (5/20엔 렌즈 없어 빛만 통과하고 형상 0이었음. 형상이 잡히면 그 문제 해결된 것)
- ⚠️ 형상 안 잡히면: 렌즈 헐거움/역방향, 노출 과다, 초점거리 밖(물체 거리 조정)

### 4) 스냅샷 남기기
- `s` 눌러 PNG 저장 (viz_output/) → 성공샷 1장 = 증빙
- 8mm 확인되면 12mm도 같은 절차로 한 번 (선택, 화각 비교용)

## ✅ 7/20 렌즈 장착·형상 검증 성공
- 8mm(C23-0824-5M) 장착 → 라이브뷰(throughput 30Mbps 기본, drop 없음, FPS 5.1)
  키보드 글자·손가락 지문·Dock 아이콘 또렷 = RGB 살아있음 확정(5/20엔 형상 0).
- OpenCV 4.13.0(Mac) = CharucoDetector 신 API 사용 가능.

## 다음 단계 A — Intrinsic 캘리브 (ChArUco)
> RGB 융합 선행조건. 정확한 fx/fy/cx/cy + 왜곡계수를 구해 ACE2_5MP_SPEC 교체.
> ⚠️ 준비물 = **ChArUco 보드 실물**(인쇄 → 평평한 판에 기포 없이 부착).

### A-1) 보드 인쇄물 생성 (Mac 또는 어디서든)
```bash
python bin_picking/tests/make_charuco_board.py --out viz_output/charuco_A4.png
```
- 기본 7x5 칸, 한 칸 30mm, DICT_5X5_250. A4에 **배율 100%(실제 크기)**로 인쇄.
- ⚠️ 인쇄 후 **자로 한 칸 실제 길이 측정** → 캘리브 시 그 실측값을 `--square-mm`로.
- 평평한 판(폼보드·아크릴·두꺼운 하드보드)에 기포 없이 부착(휘면 캘리브 오차).

### A-2) 캘리브 실행 (Mac, 카메라 연결 상태)
```bash
export BASLER_ACE2_IP=192.168.20.20
python bin_picking/tests/calibrate_ace2_intrinsics.py \
  --squares-x 7 --squares-y 5 --square-mm <실측값> --marker-ratio 0.75
```
- 라이브 뜨면 보드를 화면 모서리·중앙 골고루, ±30° 기울여, 30~60cm 거리 바꿔가며
  **SPACE로 15~25장 채택**(초록 코너 6개+ 잡힐 때만). `q`로 끝내면 자동 캘리브.
- 결과 = 재투영 RMS(<1px 양호) + fx/fy/cx/cy/dist → `config/ace2_intrinsics.json` 저장.
- 이 값으로 `basler_capture.py` `ACE2_5MP_SPEC` fx/fy/cx/cy 교체.

## 다음 단계 B — Blaze↔ACE2 extrinsic 정렬 (A 이후)
- 두 카메라가 **같은 ChArUco 보드를 동시에** 보게 하여 상대 R,t 추정 → RGB-D 정합.
- L자 듀얼 브래킷에 이미 고정됨(7/20 확인) → 정렬값 한 번 구하면 고정 재사용.
- 이후에야 RGB 융합 학습 가능. (스크립트는 A 결과 확인 후 신설 예정)

## 참고 (코드/스펙)
- 뷰어: `bin_picking/tests/live_viewer_ace2.py` (focus score = 중앙 ROI Laplacian variance)
- 스펙: `bin_picking/src/acquisition/basler_capture.py` `ACE2_5MP_SPEC`
- 상세 이력: 렌즈 입고·FOV 계산은 개발 메모리 참조
