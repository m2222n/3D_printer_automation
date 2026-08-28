# 📌 IPC-510 카메라 2대 연결 — 확립된 절차 (2026-08-28 실측)

> 🚨 **압축 금지.** 이 파일은 **다시 연결할 때 시행착오를 0으로 만드는 것**이 목적이다.
> 숫자·포트 이름·명령 하나가 빠지면 다음에 그대로 한 시간이 다시 든다
> ([[dual-camera-setup-0824]]와 같은 성격 · 그쪽은 **맥**, 이 파일은 **IPC(Windows)**).
>
> ✅ **2026-08-28 실측으로 두 대 `Open()` 성공**까지 검증된 절차다.

---

## 0. 결론부터 — 이 표만 맞추면 된다

| 카메라 | 🚨 물리 자리 | 인터페이스 이름 | 카메라 IP | **호스트(랜포트) IP** | 전원 |
|---|---|---|---|---|---|
| **Blaze-112** | **오른쪽 위에서 2번째** | `이더넷` (**Intel I219-V**) | `192.168.20.10` | **`192.168.20.1`** | 🚨 **24VDC 별도** |
| **ACE2** (a2A2448) | **제일 오른쪽 위** | `이더넷 2` (I226-V) | 🚨 **`192.168.20.20`** | **`192.168.20.2`** | 랜선(PoE 불필요·링크로 동작) |

🚨 **절대 건드리지 말 것 = `이더넷 4`** — **공장망 포트이고 원격 접속이 이걸 탄다. 뽑으면 원격이 끊긴다.**
(실제 IP는 `Get-NetIPAddress`로 확인 · 카메라 대역이 아닌 유일한 `Up` 포트다)

⭐ **Blaze가 I219-V에 꽂힌 건 오히려 좋다** — 나머지 6포트가 전부 I226-V라 **칩 이름으로 구분**된다.

---

## 1. 절차 (관리자 PowerShell)

### ① 관리자 창인지 먼저 확인 — 🚨 일반 창이면 IP를 못 박는다
```powershell
[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')
```
`True`여야 한다. 아니면 `Start-Process powershell -Verb RunAs`.
🚨 일반 창에서 `New-NetIPAddress`를 돌리면 **`액세스가 거부되었습니다`(Windows System Error 5)** 가 뜬다.
⭐ **프롬프트가 `C:\WINDOWS\system32`면 관리자 / `C:\Users\admin`이면 일반** (8/12 교훈).

### ② 전원·랜선 연결
- **Blaze = 24VDC 별도 전원**(PoE 아님). 연결하면 카메라 LED **노란불 점등 + 하나는 점멸**
  ⚠️ **그 LED는 "랜 링크/트래픽"이지 "PC에 붙었다"는 뜻이 아니다** — 스위치에 꽂아도 똑같이 켜진다
- 위 표의 **물리 자리**에 랜선을 꽂는다

### ③ 어느 인터페이스인지 확인 (추측 금지)
```powershell
Get-NetAdapter | Where-Object Status -eq 'Up' | Format-Table Name, InterfaceDescription, Status, LinkSpeed
```
🚨 **꽂자마자 찍으면 아직 `Disconnected`다**(링크 협상에 몇 초) ⇒ **안 뜨면 한 번 더 찍는다.**
⭐ 8/28에 이걸로 *"물리 문제"* 로 오판할 뻔했다. **한 대씩 꽂고 새로 `Up`이 된 이름을 확인**하면 확실하다.

### ④ 호스트 IP 고정
```powershell
New-NetIPAddress -InterfaceAlias "이더넷"   -IPAddress 192.168.20.1 -PrefixLength 24
New-NetIPAddress -InterfaceAlias "이더넷 2" -IPAddress 192.168.20.2 -PrefixLength 24
```
- ⚠️ **게이트웨이는 주지 않는다**(카메라 전용망 · 주면 기본 경로가 꼬인다)
- 이미 IP가 있어 실패하면: `Remove-NetIPAddress -InterfaceAlias "<이름>" -Confirm:$false`
- ⭐ `AddressState: Tentative`는 정상(중복검사 중) — 몇 초 뒤 `Preferred`가 된다
- ⭐ APIPA(`169.254.x`)가 같이 남아 있어도 **무해**하다

### ⑤ 🚨🚨 열거 — **반드시 GigE TL을 직접 만든다**
```powershell
C:\binpick_venv\Scripts\python.exe -c "from pypylon import pylon; tl=pylon.TlFactory.GetInstance().CreateTl('BaslerGigE'); d=tl.EnumerateAllDevices(); print(len(d)); [print(x.GetModelName(), x.GetIpAddress()) for x in d]"
```

🚨🚨🚨 **`TlFactory.GetInstance().EnumerateDevices()` 는 우리 카메라를 못 본다 — 항상 `0`이다.**
**꽂혀 있고 핑이 되는 상태에서도 `0`이다.** 반드시 위처럼 `CreateTl('BaslerGigE')` + `EnumerateAllDevices()`.
📌 8/18에 같은 버그를 겪었다(`blaze_capture_crosssession.py:123`이 `CreateTl` **반환값을 버려서** 실패,
진단 스크립트는 `gige.EnumerateAllDevices()`라 성공).

### ⑤-2 🚨🚨🚨 **Windows 방화벽을 열어야 한다 — 이게 없으면 "열리는데 영상이 안 온다"**

**한 번만 하면 된다**(영구 저장). 관리자 창:
```powershell
New-NetFirewallRule -DisplayName "GigE Vision Stream (UDP)" -Direction Inbound `
  -Protocol UDP -LocalPort Any -RemoteAddress 192.168.20.0/24 -Action Allow -Profile Any
```
⭐ **`-RemoteAddress 192.168.20.0/24`가 핵심** = **카메라 대역에서 오는 것만** 허용
⇒ 공장망·인터넷에는 영향이 없어 **방화벽을 켠 채로 안전하게 해결**된다.
✅ **방화벽 3개 프로파일 전부 `Enabled True` 상태에서 `GRAB OK` 확인**(8/28).

🚨 **왜 필요한가** = GigE 스트리밍은 **카메라가 PC로 UDP를 밀어넣는다**(인바운드).
제어 채널(열기·파라미터 설정)은 **PC가 먼저 거는 것**이라 방화벽과 무관하게 성공한다.
⇒ ⭐⭐ ***"카메라는 다 열리는데 이미지만 안 온다"** 면 거의 확실히 방화벽이다.*

🔴 **부족했던 조치**(8/28 실측 — 이것만으로는 **안 됐다**):
- `Set-NetConnectionProfile ... -NetworkCategory Private` (Public→Private 변경) → ❌
- `New-NetFirewallRule -Program "...\python.exe"` (프로그램 기반 허용) → ❌
⇒ ⭐ **포트/대역 기반 UDP 규칙**이라야 들었다.

### ⑥ 🥇 **열림까지 확인한다 — 열거 성공은 증거가 아니다**
```powershell
C:\binpick_venv\Scripts\python.exe -c "from pypylon import pylon; tl=pylon.TlFactory.GetInstance().CreateTl('BaslerGigE'); [print(d.GetModelName(), '->', (lambda c: (c.Open(), 'OK', c.Close())[1])(pylon.InstantCamera(tl.CreateDevice(d)))) for d in tl.EnumerateAllDevices()]"
```
**두 줄 다 `OK`** 여야 끝이다.

---

## 2. 🚨 안 될 때 — 순서대로 (추측하지 말 것)

```powershell
# ① 내 포트 IP가 실제로 살아있나
Get-NetIPAddress -AddressFamily IPv4 | Format-Table InterfaceAlias, IPAddress, AddressState
# ② L2에 붙었나 (MAC이 보이나)
arp -a | findstr "192.168.20"
# ③ 핑
ping -n 2 192.168.20.10
```

| 관측 | 원인 | 조치 |
|---|---|---|
| `Up`이 안 뜬다 | 링크 협상 지연 | **몇 초 뒤 다시 찍는다**(성급히 케이블 탓하지 말 것) |
| arp에 MAC 있고 핑 OK인데 **열거 0** | 🥇 **`EnumerateDevices()`를 쓴 것** | **`CreateTl('BaslerGigE')`로 바꾼다** |
| **열거는 되는데 `Open()` 실패** | 🥇 **호스트 IP 대역 불일치** | 호스트를 **카메라와 같은 대역**으로 |
| 🥇🥇 **`Open()`까지 되는데 `RetrieveResult` 타임아웃**<br>(`Grab timed out … all GigE network packets for streaming are dropped`) | 🥇 **Windows 방화벽이 인바운드 UDP 차단** | **⑤-2 UDP 규칙**을 넣는다 |
| arp에 아무것도 없음 | 케이블·전원·포트 | Blaze는 **24VDC부터** 확인 |

🚨 **grab 타임아웃을 "대역폭"으로 먼저 의심하지 말 것**(8/28에 내가 그랬다).
`--throughput 20 → 30`으로 바꿔도 **똑같이 실패**했고, **ACE2를 빼도 실패**했으며,
**스크립트를 우회한 순수 기본값 단독 grab도 실패**했다 ⇒ 대역폭·동시성·스크립트 설정 **전부 무죄**.
⭐ **가르는 방법 = 방화벽을 통째로 잠깐 끄고 재시험**(부분 조치로는 무죄/유죄가 안 갈린다).
   확인 즉시 다시 켜고 ⑤-2 규칙으로 정식 처리한다.
🐛 참고 = `--allow-no-rgb`는 **ACE2 개방을 막지 않는다**(자동 발견해서 그래도 연다)
   ⇒ **단독 시험이 안 된다.** 진짜 단독 시험은 위 §1-⑥ 같은 **한 줄 python**으로 한다.

**`Open()` 실패 시 실제 에러 문구**(8/28 실측):
```
Failed to download the XML configuration file from device
'Basler a2A2448-23gcBAS#003053381ABC#192.168.20.20:3956':
연결할 수 없는 네트워크에서 소켓 작업을 시도했습니다. (0xc0072743)
```
⚠️ **8/24에 같은 문구를 봤으나 그때 원인은 픽셀 포맷이었다** ⇒ 📌 **증상이 같아도 원인은 다르다.**

---

## 3. ⭐⭐ 이번에 새로 알게 된 것 (다음 판단의 근거)

### 🎉 Windows는 대역을 안 갈라도 된다 — 맥 결론이 여기선 성립하지 않는다

| | 맥 (8/24) | **IPC / Windows (8/28)** |
|---|---|---|
| 같은 대역에 두 포트 | 🔴 **하나만 열린다**(트래픽을 한 인터페이스로만 보냄) | 🟢 **둘 다 열린다** |
| 필요한 구성 | **대역 분리**(`.20` / `.30`) | **같은 `.20` 대역 + 호스트 IP만 다르게**(`.20.1` / `.20.2`) |

⇒ ⭐⭐ **8/24에 세 시간 쓴 그 제약이 Windows엔 없다.**
⚠️ **단 여기까지는 "열림"이고 "두 대 동시 grab 대역폭"은 미검증**이다.

### 🚨 문서의 설정값과 장비에 저장된 값이 달랐다
`.30.20`은 **문서에 적혀 있던 값**이고 카메라 실제 값은 **`.20.20`** 이었다.
⇒ ⭐ **열거 출력이 실물의 답이다.** 문서값을 전제로 호스트를 잡으면 *"열거는 되는데 안 열리는"* 상태가 된다.

### 📌 IP는 케이블이 아니라 "포트 이름"에 저장된다
포트를 옮겨 꽂으면 인터페이스 이름이 바뀌고(`이더넷 6`→`이더넷`) **거기 박아둔 IP는 따라오지 않는다.**
⇒ 🚨 **다음에도 같은 구멍에 꽂아야 한다**(그래서 §0에 물리 자리를 적어뒀다).
⭐ 맥과 반대다 — 맥은 어댑터를 뺐다 꽂으면 이름이 바뀌어 문제였고(`setup_camera_net.py`를 만든 이유),
Windows 내장 포트는 **이름이 고정**이라 한 번만 설정하면 된다.

### 🔴 `bin_picking/tests/setup_camera_net.py` 는 IPC에서 못 쓴다
**macOS 전용**이다(`ifconfig` · `en*` 파싱 · `sudo`). ⭐ 살아있는 것은 **대역 표뿐**이고,
Windows는 위 `New-NetIPAddress`로 한다.

---

## 4. ✅ 최종 검증 결과 (2026-08-28)

**두 대 동시 grab 성공** — `blaze_ace2_capture_dual.py`가 **Windows에서 그대로 돈다.**

| 항목 | 실측 |
|---|---|
| 동시 스트리밍 | 🟢 **depth + RGB 동시 표시** · `fps 5.1` |
| depth 해상도 | **(480, 848)** = 8/18 학습셋과 **동일** |
| ACE2 | `BayerRG8` · 노출 auto · RGB `bright=201 sharp=38` |
| Blaze 파라미터 | ShortRange ✅ · Spatial/Temporal/OutlierRemoval On |
| throughput | `--throughput 30`으로 성공 (기본 20도 **grab 실패와 무관**했다 — 원인은 방화벽) |

⇒ 🎯 **"카메라를 IPC에 연결한다"는 여기서 닫혔다.**
⚠️ **맥에서 필수였던 `--throughput 30` 튜닝이 Windows에서도 필요한지는 미검증**
(방화벽을 고친 뒤 30으로 한 번에 성공해서 20과의 차이를 가르지 않았다).

## 5. 다음에 이어서 할 것

- [ ] 🥇 **로봇팔 브라켓 장착 후 촬영** — 🚨 **그 전 촬영은 실운영 구도가 아니다**(eye-in-hand가 목표)
      ⇒ **손에 들고 찍은 데이터는 학습·평가에 쓰지 않는다**
- [ ] **카메라 ↔ 빈 윗면 거리 실측** — 브라켓 장착 후에 의미가 있다
- [ ] ACE2 IP를 `.30.20`으로 바꿀지 — 🔴 **바꾸지 않는다**(같은 `.20` 대역으로 둘 다 열린다)
- [ ] `--throughput` 20 vs 30 차이 — 있으면 좋지만 **급하지 않다**
- [ ] 🟢 **미리보기에서 RGB가 작게 나온다** — ⏸️ **브라켓 장착 후로 미룸**(지금 고치지 않는다)

### 🟢 미리보기 RGB가 작은 이유 = 의도한 비율이 아니라 **종횡비의 부작용**
```python
th = vis.shape[0]                           # RGB를 depth와 "같은 높이"로 맞추고
tw = int(bgr.shape[1] * th / bgr.shape[0])  # 폭은 종횡비대로 따라간다
```
| | 해상도 | 종횡비 | 같은 높이일 때 폭 |
|---|---|---|---|
| Blaze depth | 848×480 (×1.5) | **1.77**(16:9) | 1272px |
| ACE2 RGB | 2448×2048 | **1.20**(6:5) | **864px** = depth의 **68%** |

⭐ **원래 목적이 "판독"이 아니라 "정합 확인"이었다** — 코드 주석 원문 =
*"두 카메라가 같은 장면을 보는지 **눈으로 확인**"*(7/29에 화각차로 depth 86%가 ACE2 밖이었던 전례).
⇒ 📌 **지금 고치지 않는 이유** = 이 화면은 **미리보기일 뿐 인식 입력이 아니다**
(실제 입력은 `.npy` / `_rgb.png` **원본**) ⇒ **비율을 바꿔도 빈피킹 성능은 안 바뀐다.**
⭐ **브라켓 장착 후 카메라 위치가 바뀌면 "무엇이 불편한지"도 달라진다** ⇒ 그때 고치면 한 번에 끝난다
(7/30에 레지스터를 확정 전에 짰다가 무효가 된 전례와 같은 계열).
🩹 **당장 답답하면** `--scale 2.0`(전체 창이 같이 커진다 · 기본 1.5).

### ⚠️ 연결 검증 때 본 화면은 "촬영 조건"이 아니었다 (오해 방지)
검증 중 화면 = **DIST 422mm · BAND 43% · all_valid 85%** 로 **학습 조건과 한참 멀다**
(합격선 = DIST 450~460 · BAND 3~10% · all_valid 3~9%).
🚨 원인은 **주황 플라스틱 상자**(850nm 반사 → 바닥이 부품과 같은 대역에 들어온다 · 8/18에 **0/5 탈락**)
+ 빈이 화면을 가득 채운 구도. ⭐ **연결 검증이 목적이었으므로 문제가 아니다** —
다만 **`SAVE OK` 표시를 "조건 통과"로 읽지 말 것**(8/24에 현장에서 완화한 임계값 기준이다).
