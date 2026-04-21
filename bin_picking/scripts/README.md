# Basler 카메라 설치 & 스모크 테스트 스크립트

**목적**: 카메라 도착 당일 (예상 4/23 목) 현장 작업 시간 단축 — 3시간 → 1시간
**대상**: 비전 PC (Ubuntu 22.04 LTS x86_64)

---

## 파일 목록

| 파일 | 용도 |
|------|------|
| `basler_setup.sh` | pylon + Blaze 드라이버 자동 설치 + GigE 네트워크 튜닝 |
| `basler_smoke_test.py` | 카메라 연결 스모크 테스트 (9단계) |
| `README.md` | 이 문서 |

---

## 사전 준비 (홈에서 가능)

1. **드라이버 다운로드** — `docs/basler_download_checklist.md` 참조
   - pylon Camera Software Suite 8.x (Linux x86_64)
   - Blaze Supplementary Package
2. **USB 메모리에 백업**
   - `~/Downloads/basler/pylon/*.tar.gz`
   - `~/Downloads/basler/blaze/*.tar.gz`
3. **스크립트 USB 복사** — `bin_picking/scripts/` 폴더 통째로

---

## 현장 작업 순서 (카메라 도착 당일)

### ① 하드웨어 연결 (10분)
- Blaze-112 + ace2 GigE 케이블 비전 PC에 연결
- Blaze-112 전원 (PoE 또는 12V DC)
- LED 정상 점등 확인

### ② 드라이버 설치 (20분)
```bash
# USB의 basler/ 폴더를 ~/Downloads/ 로 복사
cp -r /media/usb/basler ~/Downloads/

# 설치 스크립트 실행
cd ~/3D_printer_automation
bash bin_picking/scripts/basler_setup.sh
```

스크립트가 자동으로:
1. OS/아키텍처 확인
2. pylon .deb 패키지 설치 (sudo)
3. Blaze 패키지 설치
4. GigE 네트워크 튜닝 (Jumbo Frame MTU 9000, UDP 버퍼, ufw)
5. pypylon 래퍼 확인 (프로젝트 venv)
6. 설치 검증 (pylon-config, IP Configurator, Viewer)

### ③ 카메라 IP 설정 (5분)
```bash
# pylon IP Configurator GUI 실행
ipconfigurator
# 또는
/opt/pylon/bin/ipconfigurator
```

- 카메라 2대 모두 동일 서브넷에 고정 IP 할당
  - Blaze-112: `192.168.10.10`
  - ace2: `192.168.10.11`
  - 비전 PC 이더넷: `192.168.10.1`

### ④ 스모크 테스트 (10분)
```bash
source .venv/binpick/bin/activate
python bin_picking/scripts/basler_smoke_test.py
```

9단계 자동 실행:
1. pypylon import
2. TL Factory + 장치 열거
3. Blaze-112 + ace2 식별
4. BaslerCapture.start()
5. 1프레임 캡처 (depth + color)
6. 프레임 통계 (유효 픽셀, 범위)
7. save/load 라운드트립 → `/tmp/basler_smoke/`
8. PointCloud 변환 테스트
9. main_pipeline 통과 안내

### ⑤ Full Pipeline 실행 (15분)
```bash
python bin_picking/src/main_pipeline.py \
    --basler --load /tmp/basler_smoke \
    --save-viz /tmp/basler_smoke_viz
```

L1~L5 전체 파이프라인 통과 + 시각화 PNG 생성.

---

## 각 스크립트 옵션

### `basler_setup.sh`
```bash
bash basler_setup.sh            # 전체 설치 (권장)
bash basler_setup.sh --check    # 설치 상태만 확인 (재실행 시)
bash basler_setup.sh --network  # 네트워크 튜닝만
bash basler_setup.sh --pypylon  # pypylon 설치 확인
```

### `basler_smoke_test.py`
```bash
python basler_smoke_test.py                   # 전체 (카메라 연결 필요)
python basler_smoke_test.py --skip-capture    # 장치 열거까지만
python basler_smoke_test.py --out /tmp/my_dir # 저장 경로 지정
```

---

## 트러블슈팅

### 장치 열거 0대
1. 카메라 전원 LED 확인
2. `ip addr` 로 이더넷 인터페이스 확인
3. 카메라 IP와 PC IP 동일 서브넷인지 확인
4. `sudo ufw allow 3956/udp` — GigE Discovery 포트
5. `ip link set dev <iface> mtu 9000` — Jumbo Frame

### depth 유효 픽셀 낮음 (< 30%)
- 카메라 ~ 피사체 거리 300~1500mm 범위 확인 (Blaze 최적)
- 피사체 반사율 확인 (거울/투명체는 ToF 불가)
- 주변 ToF 간섭 확인 (다른 ToF 카메라/IR 조명)

### pypylon import 실패
```bash
.venv/binpick/bin/python -m pip install pypylon
```

### 프레임 드랍 (스트림 중단)
- UDP 버퍼 증가: `sudo sysctl -w net.core.rmem_max=26214400`
- Jumbo Frame 설정 확인
- CPU 부하 확인

---

## 참고 문서

- `docs/basler_download_checklist.md` — 드라이버 다운로드 체크리스트
- `docs/meeting_0422.md` — 내일 회의 자료
- `docs/binpicking_summary.md` — Phase 5 전체 현황
- `bin_picking/src/acquisition/basler_capture.py` — 캡처 모듈 본체
