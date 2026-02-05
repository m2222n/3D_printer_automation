# WireGuard LAN-to-VPN 네트워크 연결 가이드

## 목차
1. [현재 네트워크 구조](#1-현재-네트워크-구조)
2. [목표](#2-목표)
3. [해결 방법 옵션](#3-해결-방법-옵션)
4. [방법 A: 라우터에서 라우팅 설정 (권장)](#4-방법-a-라우터에서-라우팅-설정-권장)
5. [방법 B: 6000 서버에 WireGuard 클라이언트 설치](#5-방법-b-6000-서버에-wireguard-클라이언트-설치)
6. [방법 C: ipTIME 라우터 WireGuard 클라이언트 모드](#6-방법-c-iptime-라우터-wireguard-클라이언트-모드)
7. [트러블슈팅](#7-트러블슈팅)
8. [참고 자료](#8-참고-자료)

---

## 1. 현재 네트워크 구조

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          인터넷                                              │
└─────────────────────────────────────────────────────────────────────────────┘
           │                                           │
           │                                           │
    ┌──────┴──────┐                            ┌───────┴───────┐
    │  501 오피스  │                            │     공장      │
    │   라우터     │◀═══ WireGuard 터널 ═══════▶│   공유기      │
    │ (ipTIME)    │         (UDP)               │              │
    └──────┬──────┘                            └───────┬───────┘
           │                                           │
    ┌──────┴──────────────┐                    ┌───────┴───────┐
    │  LAN: 192.168.100.x │                    │ LAN: 192.168. │
    │                     │                    │      219.x    │
    │  ┌───────────┐      │                    │ ┌───────────┐ │
    │  │ 6000 서버 │      │                    │ │  공장 PC  │ │
    │  │ .100.29   │      │                    │ │  .219.48  │ │
    │  │ (Linux)   │      │                    │ │ (Windows) │ │
    │  └───────────┘      │                    │ └───────────┘ │
    └─────────────────────┘                    └───────────────┘
```

### 현재 IP 주소 정리

| 장치 | Local IP | VPN IP | 상태 |
|------|----------|--------|------|
| 501 라우터 (WireGuard Server) | 192.168.100.1 | 10.145.113.1 | ✅ 운영 중 |
| 공장 PC | 192.168.219.48 | 10.145.113.3 | ✅ VPN 연결됨 |
| 6000 서버 | 192.168.100.29 | - | ❌ VPN 미연결 |

### 문제점

6000 서버(192.168.100.29)에서 공장 PC의 VPN IP(10.145.113.3)로 접근할 수 없음.

```bash
# 6000 서버에서 실행 시 실패
ping 10.145.113.3        # ❌ 응답 없음
curl http://10.145.113.3:44388/  # ❌ 연결 불가
```

---

## 2. 목표

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       목표: 연결 완료 후 구조                                │
│                                                                             │
│   6000 서버 (192.168.100.29)                                                │
│        │                                                                    │
│        ▼                                                                    │
│   501 라우터 (192.168.100.1 / 10.145.113.1)                                │
│        │                                                                    │
│        ▼  WireGuard 터널                                                   │
│   공장 PC (10.145.113.3)                                                   │
│        │                                                                    │
│        ▼                                                                    │
│   PreFormServer (:44388)                                                   │
│        │                                                                    │
│        ▼                                                                    │
│   3D 프린터 (Form4 x 4대)                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**목표**: 6000 서버에서 `http://10.145.113.3:44388/` 접근 가능하게 만들기

---

## 3. 해결 방법 옵션

| 방법 | 설명 | 난이도 | 권장 |
|------|------|--------|------|
| **A** | 라우터에서 Static Route 추가 | ⭐ 쉬움 | ✅ 권장 |
| **B** | 6000 서버에 WireGuard 클라이언트 설치 | ⭐⭐ 보통 | 대안 |
| **C** | ipTIME 라우터를 WireGuard 클라이언트로 설정 | ⭐⭐⭐ 어려움 | 고급 |

---

## 4. 방법 A: 라우터에서 라우팅 설정 (권장)

### 개념

501 라우터가 이미 WireGuard Server이므로, LAN에 있는 장치들이 VPN 네트워크에 접근할 수 있도록 **라우팅 규칙**만 추가하면 됩니다.

```
6000 서버 → 라우터(게이트웨이) → WireGuard 인터페이스 → 공장 PC
```

### 4.1 ipTIME 라우터 설정 (웹 인터페이스)

#### Step 1: 라우터 관리 페이지 접속
```
브라우저에서: http://192.168.100.1
또는: http://iptime.com (내부망에서)
```

#### Step 2: 고급 설정 → 라우팅 설정
```
메뉴 경로: 고급 설정 → 네트워크 관리 → 라우팅 설정
```

#### Step 3: Static Route 추가
| 항목 | 값 | 설명 |
|------|-----|------|
| 목적지 네트워크 | 10.145.113.0 | VPN 네트워크 |
| 서브넷 마스크 | 255.255.255.0 | /24 |
| 게이트웨이 | (WireGuard 인터페이스) | 라우터의 WireGuard IP |
| 메트릭 | 1 | 우선순위 |

> ⚠️ **주의**: ipTIME에서 WireGuard Server를 운영 중이라면, 이미 내부적으로 라우팅이 설정되어 있을 수 있습니다. 아래 확인 단계를 먼저 진행하세요.

### 4.2 확인: 현재 라우터의 WireGuard 설정

#### ipTIME WireGuard Server 설정 확인
```
메뉴 경로: 고급 설정 → VPN 설정 → WireGuard 서버 설정
```

확인할 항목:
- [x] WireGuard 서버 활성화 여부
- [x] VPN 내부 통신 NAT 설정 (활성화/비활성화)
- [x] 할당된 VPN IP 대역 (예: 10.145.113.0/24)

#### "VPN 내부 통신 NAT" 설정 확인

| 설정 | 동작 | 6000 서버 접근 |
|------|------|---------------|
| **활성화** | VPN 트래픽이 NAT됨 → LAN 장치도 VPN 접근 가능 | ✅ 가능 |
| **비활성화** | VPN 트래픽이 라우팅만 됨 → 추가 설정 필요 | ❌ 추가 설정 필요 |

### 4.3 6000 서버에서 라우팅 추가 (필요시)

라우터 설정만으로 안 될 경우, 6000 서버에 수동으로 라우팅을 추가합니다.

```bash
# 일시적 라우팅 추가 (재부팅 시 사라짐)
sudo ip route add 10.145.113.0/24 via 192.168.100.1

# 확인
ip route | grep 10.145.113

# 테스트
ping 10.145.113.3
```

#### 영구 라우팅 추가 (Ubuntu/Debian)

```bash
# /etc/netplan/*.yaml 파일 수정
sudo nano /etc/netplan/01-netcfg.yaml
```

```yaml
network:
  version: 2
  ethernets:
    eth0:  # 또는 실제 인터페이스 이름
      addresses:
        - 192.168.100.29/24
      gateway4: 192.168.100.1
      routes:
        - to: 10.145.113.0/24
          via: 192.168.100.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

```bash
# 적용
sudo netplan apply
```

---

## 5. 방법 B: 6000 서버에 WireGuard 클라이언트 설치

라우터 설정이 어렵거나, 6000 서버만 VPN에 연결하고 싶은 경우 사용합니다.

### 5.1 WireGuard 설치 (Ubuntu)

```bash
# 설치
sudo apt update
sudo apt install wireguard

# 설치 확인
wg --version
```

### 5.2 설정 파일 생성

Faridh님께 새로운 Peer 설정 파일을 요청해야 합니다.

**요청 내용:**
```
장치명: 6000-Server
용도: 3D 프린터 API 서버
원하는 VPN IP: 10.145.113.4 (또는 할당 가능한 IP)
```

### 5.3 설정 파일 예시

Faridh님으로부터 받을 파일 형식:

```ini
# /etc/wireguard/wg0.conf

[Interface]
Address = 10.145.113.4/24
PrivateKey = <Faridh님이 제공할 Private Key>
DNS = 203.248.252.2

[Peer]
PublicKey = UWK6c3GPmuOyDrTwrgsNUvYx9J6kM6f3S4eRatKaang=
AllowedIPs = 10.145.113.0/24
Endpoint = 106.244.6.242:56461
PersistentKeepalive = 25
```

### 5.4 WireGuard 시작

```bash
# 설정 파일 권한 설정
sudo chmod 600 /etc/wireguard/wg0.conf

# WireGuard 시작
sudo wg-quick up wg0

# 상태 확인
sudo wg show

# 연결 테스트
ping 10.145.113.3
curl http://10.145.113.3:44388/
```

### 5.5 자동 시작 설정

```bash
# 부팅 시 자동 시작
sudo systemctl enable wg-quick@wg0

# 서비스 상태 확인
sudo systemctl status wg-quick@wg0
```

---

## 6. 방법 C: ipTIME 라우터 WireGuard 클라이언트 모드

전체 LAN(192.168.100.x)을 VPN에 연결하는 방법입니다. 이 경우 라우터가 WireGuard 클라이언트로 동작합니다.

> ⚠️ **주의**: 현재 501 라우터가 이미 WireGuard **Server**로 운영 중이므로, 이 방법은 구조 변경이 필요합니다. 신중하게 검토 필요.

### 6.1 ipTIME WireGuard 클라이언트 설정

```
메뉴 경로: 고급 설정 → VPN 설정 → WireGuard 클라이언트 설정
```

참고: [ipTIME 공식 WireGuard 클라이언트 가이드](https://iptime.com/iptime/?page_id=67&uid=25263&mod=document)

### 6.2 Site-to-Site VPN 고려사항

두 네트워크를 완전히 연결하려면:

1. **IP 대역 충돌 방지**: 양쪽 LAN이 다른 대역이어야 함
   - 501 오피스: 192.168.100.x ✅
   - 공장: 192.168.219.x ✅ (다름 → OK)

2. **AllowedIPs 설정**: 양쪽에서 상대방 네트워크를 AllowedIPs에 추가

3. **방화벽 규칙**: 양쪽에서 해당 트래픽 허용

---

## 7. 트러블슈팅

### 7.1 연결 테스트 순서

```bash
# Step 1: 라우터 연결 확인
ping 192.168.100.1

# Step 2: VPN 인터페이스 연결 확인 (라우터에서)
ping 10.145.113.1

# Step 3: 공장 PC VPN IP 연결 확인
ping 10.145.113.3

# Step 4: PreFormServer 포트 확인
curl http://10.145.113.3:44388/
```

### 7.2 일반적인 문제 및 해결

| 문제 | 원인 | 해결 |
|------|------|------|
| ping 10.145.113.3 실패 | 라우팅 없음 | 라우터 또는 서버에 라우팅 추가 |
| ping 성공, curl 실패 | 방화벽 | 공장 PC Windows 방화벽에서 44388 포트 허용 |
| 간헐적 연결 끊김 | NAT 타임아웃 | PersistentKeepalive = 25 설정 |
| 느린 속도 | MTU 문제 | MTU를 1420으로 설정 |

### 7.3 Windows 방화벽 설정 (공장 PC)

공장 PC에서 44388 포트가 VPN 네트워크에서 접근 가능하도록 설정:

```powershell
# PowerShell (관리자 권한)
New-NetFirewallRule -DisplayName "PreFormServer VPN" -Direction Inbound -Protocol TCP -LocalPort 44388 -RemoteAddress 10.145.113.0/24 -Action Allow
```

또는 Windows 방화벽 GUI에서:
1. Windows Defender 방화벽 → 고급 설정
2. 인바운드 규칙 → 새 규칙
3. 포트 → TCP 44388
4. 연결 허용
5. 모든 프로필 선택
6. 이름: "PreFormServer VPN"

### 7.4 라우팅 테이블 확인

```bash
# Linux (6000 서버)
ip route
traceroute 10.145.113.3

# Windows (공장 PC)
route print
tracert 10.145.113.1
```

---

## 8. 참고 자료

### 공식 문서
- [WireGuard 공식 사이트](https://www.wireguard.com/)
- [ipTIME WireGuard 서버 설정 (Windows)](https://iptime.com/iptime/?page_id=67&uid=25261&mod=document)
- [ipTIME WireGuard 클라이언트 설정](https://iptime.com/iptime/?page_id=67&uid=25263&mod=document)
- [ipTIME WireGuard 모바일 설정](https://iptime.com/iptime/?page_id=67&uid=25209&mod=document)

### 기술 가이드
- [Ubuntu WireGuard Site-to-Site VPN](https://ubuntu.com/server/docs/wireguard-vpn-site-to-site)
- [WireGuard Site-to-Site Configuration (Pro Custodibus)](https://www.procustodibus.com/blog/2020/12/wireguard-site-to-site-config/)
- [pfSense WireGuard Site-to-Site](https://docs.netgate.com/pfsense/en/latest/recipes/wireguard-s2s.html)
- [LAN-to-LAN VPN using WireGuard](https://cosmicpercolator.com/2020/04/06/lan-to-lan-vpn-using-wireguard/)

### 한국어 자료
- [퀘이사존 - ipTIME WireGuard VPN 서버 설정](https://quasarzone.com/bbs/qf_net/views/113537)
- [클리앙 - Wireguard로 사무실과 집 내부망 묶기](https://www.clien.net/service/board/cm_nas/18896329)
- [서버포럼 - WireGuard 내부망 질문](https://svrforum.com/svr/1231592)

---

## 요약: Faridh님께 전달할 내용

### 권장 방법: 방법 A (라우터 설정)

1. **확인 필요**: ipTIME 라우터의 "VPN 내부 통신 NAT" 설정이 활성화되어 있는지
2. **활성화 안 되어 있다면**: 활성화하면 LAN 장치들이 VPN 접근 가능
3. **그래도 안 되면**: 6000 서버에 수동 라우팅 추가
   ```bash
   sudo ip route add 10.145.113.0/24 via 192.168.100.1
   ```

### 대안: 방법 B (6000 서버에 WireGuard 설치)

새 VM을 만드시는 것보다, 기존 6000 서버에 WireGuard 클라이언트를 설치하는 것이 더 빠를 수 있습니다.

필요한 것: 6000 서버용 WireGuard Peer 설정 파일 (10.145.113.4)

---

**문서 작성일**: 2026-02-05
**작성자**: 정태민
**프로젝트**: 3D프린터-로봇 연동 자동화 시스템
