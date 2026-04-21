# 3D 빈피킹 비전 시스템 개발 진행 현황

**ORINU-DEV-2026-002**
Phase 5 — 후공정 빈피킹 자동화

2026년 4월 17일 | 오리누 주식회사 정태민 연구원 | jtm@orinu.ai

> 4/10 보고서 이후 변경사항만 기술

---

## 1. RealSense D435 실데이터 검증

D435 라이브 연동 성공 (USB 3.2, pyrealsense2 v2.57.7 소스빌드). 프레임 저장/로드 기능(`--save`/`--load`) 추가하여 카메라 없는 환경에서도 재현 가능.

### D435 실데이터 L1~L3 테스트 (일반 사물)
| 단계 | 결과 |
|------|------|
| L1 캡처 | 186K 유효 depth (61%), range 175~4538mm |
| L2 전처리 | 154K → 10,425 pts (SOR + 3mm 다운샘플 + 바닥 제거) |
| L3 분할 | **11 클러스터** (노이즈 333pts만) |
| 소요 시간 | 0.29s |

### D435 Full Pipeline L1~L5 테스트 ★
2회 실행 모두 **ACCEPT 0** — CAD 미등록 물체 오탐 없음. RMSE 3mm 임계값이 안전장치 역할 (fitness 0.47도 RMSE에서 차단).

| | 1차 (신규 촬영) | 2차 (기존 프레임) |
|---|---|---|
| 유효 depth | 88% (271K) | 61% (186K) |
| 클러스터 | 8 | 6 |
| ACCEPT/WARN/REJECT | 0/3/5 | 0/4/2 |
| 총 시간 | 1.83s | 0.89s |

---

## 2. E2E 실패 케이스 시각화

대표님 요청(4/10)에 따라 `e2e_viz.py` 모듈 구현 (~450줄).

- GT↔클러스터 매칭 → CORRECT / MISMATCH / MISSED / FALSE_POS 자동 분류
- 3종 이미지 자동 생성:
  1. `overview.png` — 전체 씬 (초록=정답, 빨강=오매칭, 파랑=미검출)
  2. `cluster_{id}.png` — 클러스터별 매칭 상세
  3. `failure_{id}.png` — 오매칭 좌우 비교 (GT vs 매칭 결과)
- `--save-viz` 옵션으로 실행

---

## 3. eye-in-hand 캘리브레이션 설계

대표님 피드백(4/10): 고정 카메라 1대 + **로봇암 장착 카메라 1대** (인식 실패 시 다른 각도에서 재촬영)

- `HandEyeCalibrator` eye-in-hand 모드 확장
  - eye-to-hand: `T_cam_to_base` (기존)
  - eye-in-hand: `T_cam_to_gripper` (신규)
- 카메라 프리셋 (Blaze-112, ace2-5mp, D435)
- 시뮬 결과: horaud 방식 **회전 0.28°, 이동 0.57mm** PASS

---

## 4. HCR-10L 로봇 교육 1회차

펜던트(Rodi) 기본 + Modbus TCP 통신 + 자동화 기본 개념. 교육 자료: `PLC_Cobot_Modbus_Guide.pdf` (34p).

### 핵심 확인사항
- 한화 HCR은 **펜던트로만 프로그래밍** (스크립트 버그 많아 미사용)
- 외부 PC는 Modbus TCP 레지스터 간접 제어만 가능
- 사용자 레지스터: 130~255 (R/W, 16bit)
- TCP 좌표 읽기: 400~405 (1/10mm, 1/10deg)
- Program State: 600, Command: 700/701/702

### 로봇 코드 정비
- `grasp_database.yaml`: robot 섹션 (HCR-10L 스펙, 관절 제한, TCP 오프셋 TBD)
- `grasp_planner.py`: `validate_pick()` 안전 검증 (작업 영역/Z충돌/힘 제한)
- `modbus_server.py`: 오일러 ZYX 명시, 피킹 사이클 문서화, `wait_for_done()`
- `hand_eye_calibration.py`: `set_tcp_offset()`, `load_tcp_offset_from_yaml()`

---

## 5. Modbus 레지스터 맵 INT16 재설계 ★

4/14 교육에서 확인된 HCR-10L 실제 스펙에 맞게 전면 재설계.

| 항목 | 이전 | 이후 |
|------|------|------|
| 레지스터 주소 | 40001~ | **130~140** (HCR 사용자 영역) |
| 좌표 인코딩 | FLOAT32 (2레지스터) | **INT16 (1레지스터, 1/10mm)** |
| 로봇 상태 | CMD 공유 | **별도 Reg 150~151** |
| 로봇 내장 매핑 | 없음 | **400~405, 600, 700~702** |
| 동기화 | 없음 | **시퀀스 번호 (Reg 140)** |

---

## 6. Colored ICP 파이프라인

`pose_estimator.py`에 Colored ICP 옵션 추가 — FPFH만으로 구분 못 하는 유사 형상 부품 변별력 향상.

- `use_colored_icp=True` 기본: 양쪽 컬러 있으면 Colored ICP, 없으면 Point-to-Plane 자동 폴백
- multi-scale: 4mm → 2mm → 1mm coarse-to-fine
- `lambda_geometric=0.968`
- hard 난이도(60%) → 카메라 입고 후 RGB 데이터로 개선 기대

---

## 7. Basler Blaze-112 + ace2 듀얼 캡처 모듈

`basler_capture.py` 신규 — RealSenseCapture와 동일 인터페이스.

- Blaze-112(ToF depth) + ace2(RGB 5MP) 듀얼 캡처
- ace2 없이 단독 동작 지원, color→depth 자동 리사이즈
- save/load 라운드트립, 시뮬 프레임 생성
- `main_pipeline.py`에 `--basler` 옵션 추가

---

## 8. 웹 서비스 인프라

- **systemd 자동시작**: formlabs-web.service (포트 8085, Restart=always, linger)
- **카카오 VM 이전**: 61.109.239.142:8085 — Cloud API 폴링 + 프론트엔드 정상
- **Basic Auth 구현**: Raw ASGI 미들웨어, HTTP+WebSocket 보호
- **한솔 코드 머지 2차**: 자동화 CMD 프린터 할당 기능 (이예승 사원)
- 공장 PC 연결은 도메인 확정 후 Cloudflare Tunnel로 진행 예정

---

## 9. Phase B 상태 변경

| 작업 | 4/10 | 4/17 |
|------|------|------|
| D435 실데이터 검증 | 대기 | **✅ 완료** (Full Pipeline PASS) |
| Modbus TCP 프로토콜 | 대기 | **✅ 완료** (INT16 재설계) |
| Colored ICP | 미착수 | **✅ 구현** (실검증은 카메라 후) |
| Basler 캡처 모듈 | 미착수 | **✅ 구현** (시뮬 PASS) |
| HCR-10L 로봇 교육 | 미착수 | **✅ 1회차 완료** |
| E2E 시각화 | 미착수 | **✅ 구현** |
| eye-in-hand 설계 | 미착수 | **✅ 설계+시뮬 완료** |
| 카메라 입고 + 실연동 | 대기 | 대기 (5월) |
| 핸드-아이 캘리브레이션 실측 | 대기 | 대기 |
| HCR-10L 실전 피킹 | 미착수 | 대기 |

---

## 10. 다음 단계

- **실물 SLA 부품 확보** → D435 촬영 → CAD 매칭 ACCEPT 검증 (REJECT만 확인됨)
- **카메라 입고 (5월)** → Basler 실연동 + Colored ICP 실데이터 + 캘리브레이션 2세트
- **HCR-10L 티칭 교육** (추후 별도 스케줄) → 펜던트 프로그램 설계
- TBD: TCP 오프셋, 작업 영역, 오일러 컨벤션 (그리퍼 장착 + 빈 배치 후 실측)
