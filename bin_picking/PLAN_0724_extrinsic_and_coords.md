# 7/24(금) 사무실 작업 계획 — extrinsic 정렬 → 좌표 출력

> **목표(태민님 7/23)**: 실제 카메라 연동해서 빈피킹이 실환경에서 돌아가게. **순서 = ① extrinsic 정렬 먼저 → ② 좌표 출력.**
> 북극성: 학습 잘 됨 → **카메라 잘 인식** → 로봇 빈피킹. 오늘은 "카메라 잘 인식"의 RGB-D 정합 + 좌표 단계.
> ⚠️ 관련 메모리: `project_ace2_camera.md` §B단계 / `project_binpicking_overview.md` / `project_hansol_coord_spec_0520.md`(6요소)

---

## 사전 체크 (도착 직후 5분)

- [ ] Blaze + ACE2 **L자 듀얼 브래킷 고정** 확인(7/20 이미 고정됨 → extrinsic 1회만 구하면 재사용)
- [ ] 두 카메라 네트워크 연결: **ACE2 = en8 / 192.168.20 대역**, **Blaze = en10 / 192.168.30 대역**
- [ ] ACE2 intrinsic json 존재 확인: `bin_picking/config/ace2_intrinsics.json` (⚠️Mac 상주, RMS 0.546px)

---

## 단계 ① — Blaze↔ACE2 extrinsic 정렬 (7/20에 막혔던 것 마무리)

### 1-1. 네트워크 재설정 (재부팅 시 매번 — ForceIp는 임시라 소멸)
```bash
sudo ifconfig en10 192.168.30.1
python bin_picking/tests/find_blaze.py --force-ip 192.168.30.10
```
→ Blaze가 열거·연결되는지 먼저 확인. (⚠️ Basler ToF는 ICMP 무응답 = ping으로 판단 금지, pypylon 열거가 정답)

### 1-2. extrinsic 정렬 실행
```bash
python bin_picking/tests/calibrate_blaze_ace2_extrinsic.py \
  --square-mm 25 --blaze-ip 192.168.30.10 \
  --blaze-exposure 400 --min-corners 4
```
- 원리: 두 카메라가 **같은 ChArUco 보드**를 동시에 봄 → 각자 solvePnP → 상대변환 T_ace2_to_blaze 평균.
- Blaze는 **intensity(적외선 흑백)** 컴포넌트로 보드 검출.
- **BOTH OK** 뜰 때 SPACE → **5~8쌍** 수집 → `q` 저장.
- 산출물: `bin_picking/config/blaze_ace2_extrinsic.json` (baseline mm·spread mm)

### ⚠️ 7/20 미해결 관문 2개 + 대응책 (이게 오늘의 실제 난관)
| 관문 | 증상 | 대응 |
|------|------|------|
| **Blaze intensity 조명 민감** | 850nm 직사광 과노출 → 흑백 칸 대비 소실 → 검출 실패 | **조명 등지기** + `--blaze-exposure 400`(안 되면 200~800 스윕) |
| **두 카메라 화각 차** | Blaze 광각·저해상(848×480) / ACE2 8mm 좁음 → 동시 6+ 코너 안 뜸 | `--min-corners 4`로 이미 완화. 안 되면 ⓐ**A3 보드**로 키우기 ⓑ카메라를 보드에서 **더 멀리** ⓒ보드를 두 화각 겹치는 중앙에 |

### 🔑 오늘의 판단 포인트
- 위 관문이 안 풀리면 **시간 못 잡아먹게** → 대안: Blaze intrinsic을 먼저 제대로 캘리브(현재 FOV 추정값 fx553…이라 정확도 낮음)하거나, 정렬 정확도 목표를 낮춰(±수mm) 일단 좌표 단계로 넘어가서 E2E를 닫고 정밀도는 나중에.

---

## 단계 ② — 좌표 출력 (정렬 성공 후)

### 2-1. 인식 → 3D 좌표
- 파이프라인: ACE2 RGB로 부품 인식(depth_track 또는 yolo_track) → 픽셀 좌표를 depth(Blaze)와 정합 → 3D 좌표.
- extrinsic이 있어야 Blaze depth ↔ ACE2 RGB 픽셀이 정합됨.

### 2-2. 6요소 좌표 (한솔 명세 = `project_hansol_coord_spec_0520.md`)
```
x, y, z, edge, angle, label
```
- 출력 코드: `bin_picking/yolo_track/pipeline/detect_and_output.py` (기존 582줄, 6요소 YAML/JSON)
- 좌표계: 카메라 기준 → (나중) 로봇 Base/TCP 변환. 오늘은 **카메라 좌표계 6요소 출력까지가 목표**.

### 2-3. 검증
- 실제 빈에 부품 놓고 → 인식 → 좌표 뽑기 → 눈으로/자로 대략 맞는지 확인(±cm 수준이라도 파이프라인이 닫히는 게 우선).

---

## 오늘 성공 기준 (현실적)
1. ✅ **최소**: extrinsic json 1개 확보(BOTH OK 5쌍 이상) → RGB-D 정합 가능해짐.
2. ✅ **목표**: 실 부품 1개를 실카메라로 인식 → 6요소 좌표 출력 1건.
3. ⏭️ **다음(로봇 E2E)**: 좌표 → Modbus → HCR-10L 전송·피킹은 로봇 전원·펜던트 준비 후(가을 페이스 or 앞당김).

## ⚠️ 함정 메모 (7/20 교훈)
- ForceIp는 재부팅 시 소멸 → 매번 en10 30번대 + find_blaze 먼저.
- Blaze GevSCPD Max=96 (1000 넣으면 OutOfRange).
- 캘리브 촬영은 **노출 짧게(3ms) + SPACE 직전 0.5초 정지**(모션블러가 RMS 주범).
- 간헐 성공 ≠ 성공 → 연속 성공률로 검증.
