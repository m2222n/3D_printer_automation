# Basler pylon + Blaze-112 드라이버 다운로드 체크리스트

**목적**: 카메라 도착 당일(예상 4/23 목) 네트워크/다운로드 지연 방지
**작성**: 2026-04-21 (월)

---

## 1. Basler 계정 (선행 조건)

- [ ] Basler 계정 확인 / 가입
  - URL: https://www.baslerweb.com/en/my-baslerweb/
  - 없으면 무료 가입 (회사 이메일 `jtm@orinu.ai` 권장)
  - 가입 후 로그인 상태 유지

---

## 2. pylon Camera Software Suite (Linux x86_64)

**대상 OS**: Ubuntu 22.04 LTS (비전 PC 스펙)
**버전**: 8.x (최신 안정판)

- [ ] 다운로드 페이지 접속
  - URL: https://www.baslerweb.com/en/downloads/software-downloads/
  - 필터: **"pylon Software"** + **"Linux x86 (64 bit)"**
- [ ] 파일 다운로드 (택1)
  - [ ] `pylon_<version>_linux-x86_64_debs.tar.gz` — **.deb 패키지 (Ubuntu 권장)**
  - [ ] `pylon_<version>_linux-x86_64.tar.gz` — 일반 tar (수동 설치)
- [ ] EULA 수락 (다운로드 시 팝업)
- [ ] 저장 경로: `~/Downloads/basler/pylon/`

### 참고
- pypylon은 Python 래퍼라 이미 `pip install pypylon==26.x`로 설치됨
- **pylon Camera Software Suite**는 GenTL 프로듀서 + Viewer + IP Configurator 포함
- `pylon IP Configurator` GUI로 카메라 IP 설정 필수

---

## 3. Blaze-112 Supplementary Package

**목적**: Blaze-112 ToF 카메라 전용 드라이버 (기본 pylon에 미포함)

- [ ] 다운로드 페이지 접속
  - URL: https://www.baslerweb.com/en/downloads/software-downloads/
  - 필터: **"Blaze"** 또는 **"ToF"** + **"Linux"**
- [ ] 파일 다운로드
  - [ ] `Basler_blaze_<version>_linux-x86_64.tar.gz` 또는 `.deb`
- [ ] 저장 경로: `~/Downloads/basler/blaze/`

### 파일명 예시
- `Basler_blaze_2.3.0_linux-x86_64.tar.gz`
- Blaze 전용 SDK (`genicam_blaze.xml`, `Blaze.dll` 대응 Linux `.so`)

---

## 4. ace2 5MP (a2A2448-23gcBAS) 관련

- [ ] **별도 패키지 불필요** — 표준 pylon에 포함됨
- [ ] 데이터시트 참고용 다운로드
  - URL: https://www.baslerweb.com/en/shop/a2a2448-23gcbas/
  - Datasheet PDF → `~/Downloads/basler/docs/`

---

## 5. Blaze-112 Application Note (학습 자료)

- [ ] Blaze 시리즈 문서 검색
  - URL: https://docs.baslerweb.com/blaze-101 (버전별 유사)
  - "Application Note", "Getting Started", "ToF Cameras Operator's Manual"
- [ ] PDF 저장: `~/Downloads/basler/docs/`

---

## 6. GigE 관련 준비 (선택)

### Jumbo Frames 설정 (GigE 성능)
- [ ] `sudo ip link set dev <iface> mtu 9000` 명령어 숙지
- pylon 설치 시 자동 안내됨

### 네트워크 설정 메모
- Blaze-112 + ace2 각각 별도 GigE 포트 필요
- 카메라 IP는 동일 서브넷, 고정 IP 권장 (예: 192.168.10.10, 192.168.10.11)
- 비전 PC GigE 인터페이스: 192.168.10.1

---

## 7. 다운로드 완료 후 확인

### 최종 디렉토리 구조 (예시)
```
~/Downloads/basler/
├── pylon/
│   └── pylon_8.x.x_linux-x86_64_debs.tar.gz
├── blaze/
│   └── Basler_blaze_2.x.x_linux-x86_64.tar.gz
└── docs/
    ├── Basler_pylon_Installation_Guide.pdf
    ├── Blaze_Application_Note.pdf
    └── a2A2448-23gcBAS_datasheet.pdf
```

### 체크섬 확인 (선택, 무결성 검증)
- [ ] Basler 다운로드 페이지에 SHA256 있으면 기록
- [ ] `sha256sum <파일>`로 검증

---

## 8. 비전 PC 입고 시 전달

- [ ] USB 메모리 또는 공유 드라이브로 비전 PC에 이관
- [ ] 공장 네트워크가 느리거나 차단된 경우 대비

---

## 9. 트러블슈팅 사전 숙지

- Jumbo Frame 미설정 시 프레임 드랍 → MTU 9000 필수
- 방화벽 (ufw) GigE Vision 포트 차단 가능 → Discovery 포트 3956 UDP 허용
- USB 3.0 ace2 모델은 `usbfs_memory_mb` 권한 설정 필요 (GigE ace2는 해당 없음)
- Blaze-112는 Power over Ethernet (PoE) 또는 12V DC 전원 필요 — 어댑터 확인

---

## 예상 다운로드 총량

- pylon: ~200 MB
- Blaze 패키지: ~50 MB
- 문서: ~30 MB
- **합계: ~300 MB** (광 인터넷 10분 내)

---

## 다음 단계 (다운로드 후)

1. `scripts/basler_setup.sh` — 자동 설치 스크립트 작성 (작업 2)
2. `scripts/basler_smoke_test.py` — 카메라 연결 스모크 테스트 (작업 2)
3. 현장에서 USB로 비전 PC에 이관 → 스크립트 실행 → 3시간 → 1시간으로 단축
