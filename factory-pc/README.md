# Factory PC Scripts

> 공장 Windows PC에서 실행되는 스크립트

## 개요

공장에 설치된 Windows PC에서 PreFormServer와 함께 실행되는 유틸리티 스크립트입니다.

## 파일 목록

| 파일 | 용도 | 포트 |
|------|------|------|
| `file_receiver.py` | 서버에서 전송한 STL 파일을 수신하여 로컬에 저장 | 8089 |

## file_receiver.py

FastAPI 백엔드 서버가 STL 파일을 공장 PC로 전송할 때, 이 스크립트가 파일을 수신하여 `C:\STL_Files` 폴더에 저장합니다.

### API

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/upload` | STL 파일 수신 (헤더: `X-Filename`, Body: 바이너리) |
| `GET` | `/` | 서버 상태 확인 |

### 실행 방법

```bash
python file_receiver.py
# File receiver running on port 8089
# Save directory: C:\STL_Files
```

### 자동 시작 설정 (Windows)

시작 폴더에 바로가기 생성 (Run: Minimized):
```
대상: pythonw file_receiver.py
시작 위치: C:\Users\devfl\
```

## 공장 PC 서비스 구성

공장 PC에서는 다음 3종이 자동 시작됩니다:

| 서비스 | 자동 시작 방식 | 포트 |
|--------|---------------|------|
| WireGuard VPN | Windows 서비스 | - |
| PreFormServer | 시작 프로그램 | 44388 |
| file_receiver.py | 시작 폴더 바로가기 | 8089 |
