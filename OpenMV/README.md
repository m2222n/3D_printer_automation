# OpenMV (Phase 4)

> 세척기/경화기 완료 감지용 OpenMV 카메라 참고 자료

## 개요

OpenMV AE3 카메라를 활용하여 Form Wash(세척기), Form Cure(경화기)의 작업 완료를 자동 감지하는 시스템입니다.

- Form Wash/Cure는 공식 API를 제공하지 않아, 카메라 기반 영상 감지로 해결
- OpenMV 카메라 내부(MicroPython)에서 직접 AI 추론 후 서버에 완료 신호 전송

## 카메라 배치 계획 (4대)

| 카메라 | 설치 위치 | 감지 내용 |
|--------|----------|----------|
| OpenMV #1 | 세척기 1번 전면 | 세척 중/완료 (바스켓 회전 여부) |
| OpenMV #2 | 세척기 2번 전면 | 세척 중/완료 (바스켓 회전 여부) |
| OpenMV #3 | 경화기 1번 전면 | 경화 중/완료 (UV LED 발광 여부) |
| OpenMV #4 | 경화기 2번 전면 | 경화 중/완료 (UV LED 발광 여부) |

## 통신 아키텍처

```
[OpenMV #1~#4] → WiFi → MQTT → [Mosquitto 브로커] → [FastAPI 서버] → [HCR 로봇]
```

## 추천 모델

- **OpenMV AE3** ($85): Alif E3 (듀얼 Cortex-M55 + 듀얼 Ethos-U55 NPU), WiFi/BT 내장, 0.25W
- **학습 플랫폼**: Edge Impulse (OpenMV 1등급 공식 지원, Classification 권장)
- **모델 포맷**: Quantized int8 TFLite

## 이 폴더 내용 (대표님 제공 자료)

| 파일/폴더 | 설명 |
|----------|------|
| `firmware_OPENMV_AE3/` | OpenMV AE3 펌웨어 (v4.8.1) |
| `openmv-ide-windows-4.8.4.exe` | OpenMV IDE 설치 파일 |
| `OpenMV-Dev-Guidance-V1.0.docx` | OpenMV 개발 가이드 문서 |
| `Python Scripts/` | 샘플 MicroPython 스크립트 |
| `Ref Webpage.txt` | 참고 웹페이지 링크 |

## 참고 링크

- [OpenMV 공식 홈페이지](https://openmv.io/)
- [OpenMV GitHub](https://github.com/openmv/openmv)
- [Edge Impulse](https://www.edgeimpulse.com/)

## 상태

현재 리서치 완료, 개발 대기 중 (Phase 2 UI 완료 후 전환 예정)
