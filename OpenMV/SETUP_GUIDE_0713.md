# OpenMV AE3 세팅·학습·검증 가이드 (2026-07-13)

> 목적: 세척기/경화기 완료 감지를 OpenMV로 **직접 써보고 검증**.
> 배경: 4/14 대표님이 MaixCAM으로 전환 지시했으나, 실제로 둘 다 손에 쥐고 비교한 적 없음 →
>   OpenMV 먼저 동작·학습시켜 성능을 실측하고 MaixCAM과 비교(더 나은 걸로 최종).
> ⚠️ 실물 카메라 작업 = **Mac/PC에서 태민님 직접**(OpenMV IDE, USB 연결). 6000(원격) 불가.

## 지금까지 준비된 것 (6000에서 완료)
- ✅ **학습 이미지 350장 추출 완료** (`OpenMV/training_images/`, 6클래스):
  wash_idle 28 / wash_running 95 / wash_complete 44 / cure_idle 36 / cure_running 125 / cure_complete 22
  (3/16 촬영 영상 6개 → `extract_frames.py`로 0.5초 간격, 240×240 중앙크롭)
- ⚠️ 밝기만으로는 클래스 구분 약함(idle 163 vs running 139) → **학습해봐야 감지력 판정 가능**
- ⚠️ complete 클래스 소수(22/44) → 실물 촬영으로 보강 권장

## A. 학습 (카메라 없이 지금 가능 — Edge Impulse)
1. [edgeimpulse.com](https://edgeimpulse.com) 프로젝트 생성 (무료)
2. `training_images/` 6개 폴더를 **라벨별 업로드** (폴더명=라벨 자동 인식)
   - Mac으로 가져가려면: 6000 → Mac scp (`~/Desktop`, [[feedback-macbook-download-desktop]])
3. Impulse 설계: Image (240×240) → **Transfer Learning (Images)** 또는 Classification
4. 학습 → **int8 quantized** → OpenMV용 **.tflite + labels.txt** 내보내기
   - Edge Impulse "OpenMV" 배포 옵션 = `.tflite` + `labels.txt` + 예제 .py 한 번에

## B. OpenMV 실물 세팅 (Mac/PC 현장)
1. **IDE 설치**: `openmv-ide-windows-4.8.4.exe` (Mac이면 openmv.io에서 macOS판)
2. **펌웨어**: OpenMV AE3 USB 연결 → IDE가 펌웨어 확인/업데이트 (폴더 `firmware_OPENMV_AE3/` v4.8.1 보유)
3. **라이브뷰 확인**: IDE 연결 → 프레임 버퍼에 세척기/경화기 화면 뜨는지 (카메라 살아있음 확인)
4. **WiFi/MQTT 설정**: `scripts/config.py`에 WiFi SSID/PW + MQTT 브로커 주소 입력
   ⚠️ config.py는 credentials 들어가므로 **git 커밋 금지**(실값은 로컬만)

## C. 감지 배포 (학습 후)
1. Edge Impulse에서 받은 `.tflite` + `labels.txt`를 OpenMV 플래시에 복사
2. 감지 스크립트 = 기존 `scripts/wash_detector.py` / `cure_detector.py` 재활용
   (모델 로드 → 추론 → 상태 변화 시 MQTT publish, 3/16 작성분)
3. `scripts/boot.py` = 전원 ON 시 자동 실행 설정
4. **완료 감지 → MQTT → 서버** 흐름 테스트 (`scripts/test_wifi_mqtt.py`로 통신 먼저 검증)

## D. 학습 데이터 보강 (선택, 실물)
- `scripts/capture_training_images.py` = 세척기/경화기 앞에서 라벨별(1/2/3) 실물 촬영
  → complete 클래스 등 부족분 보강 → Edge Impulse 재학습

## 판정 = OpenMV 써볼 가치 확인
- ✅ 학습 정확도 높고(예: 90%+) 실시간 추론 되면 → OpenMV로 충분, MaixCAM 비교 불필요할 수도
- ⚠️ idle↔running↔complete 혼동 심하면 → 밝기·화각·조명 문제 or 카메라 성능 한계
  → MaixCAM(1 TOPS NPU, 더 강력)으로 비교 필요 → [[maixcam-monitoring]]

## 자산 위치
- 학습 이미지: `OpenMV/training_images/` (git 제외 = 대용량)
- 스크립트: `OpenMV/scripts/` (capture·detector·boot·config·test_wifi_mqtt)
- 펌웨어·IDE·영상: `OpenMV/` (대표님 제공)
- 설계: `docs/Phase4_OpenMV_개발설계서.md`
