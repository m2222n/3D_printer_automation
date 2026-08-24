# 🖥️ IPC-510 세팅 카드 — 8/26(화) 재택 오전

> 🎯 **목표** = 금요일(8/29)에 IPC에서 **로봇 + 카메라 + 인식**이 한 자리에서 돌게 만든다.
> 🚨 **이것이 hand-eye의 선행조건**이다 — 로봇은 지금 공장 PC에 붙어 있고 배포 대상은 IPC다.
> 공장 PC에서 먼저 하면 **나중에 IPC에서 다시 해야 한다.**
>
> ⚠️ **원격으로 되는 것과 안 되는 것을 갈라놨다.** 오전에 원격분을 끝내면
> 금요일엔 **케이블만 옮겨 확인**하면 된다.

## 0. 접속 (10분)

```
Tailscale IPC : 100.115.122.38   (맥 100.119.119.14 · tailnet jtm.flickdone@gmail.com)
RDP 계정      : admin + 비번(8/12 신설)
```
🚨 **잠금화면 상태에서도 접속된다**(8/12 검증). 안 되면:
- 방화벽 ICMP → 3389 Listen 여부 → **`TermService`가 `Manual`이 아닌지**(8/12 원인 3개)
- `Get-Service TermService` 로 확인. 🚨 **PowerShell `sc`는 `Set-Content` 별칭**이라 쓰지 말 것

## 1. 현재 상태 확인 (10분) — 🚨 추측하지 말고 찍어본다

```powershell
python --version
python -c "import numpy, torch, PIL, scipy, cv2, yaml; print('OK')"
python -c "import pypylon; print('pypylon OK')"
cd D:\...\3D_printer_automation ; git log --oneline -3
```

**8/14에 설치해 둔 것**(기록) = Python **3.12.8** · torch **+cpu** · numpy **1.26.4** ·
tqdm · pillow · scipy

## 2. 새로 필요한 것 = **3개뿐** (20분)

⭐ **import 전수 추출로 확인한 실제 의존성**(8/14 교훈 = *"requirements.txt를 믿지 않는다"*):

| 패키지 | 왜 |
|---|---|
| **`opencv-python`** (`cv2`) | E2E 러너·전처리 |
| **`pyyaml`** (`yaml`) | grasp DB·설정 로드 |
| **`pypylon`** | 🚨 **카메라 실취득** — 이것만 금요일에 실물 검증이 필요 |

```powershell
pip install opencv-python pyyaml pypylon
```

⚠️ `blenderproc`·`bpy`·`trimesh`·`h5py`·`pyrender`·`matplotlib`·`skimage`는
**합성 데이터 생성용**이라 IPC에 불필요하다.

## 3. 코드 최신화 (10분)

```powershell
git pull        # origin/main = 60cdc00 이후 (8/24 push 완료)
```
🚨 **8/24 교훈** — 6000에서 만든 것은 **push 안 하면 다른 데서 안 보인다.**
지금은 push돼 있으니 pull로 최신이 온다.

## 4. ⭐ 결과 대조 = **이 세팅의 합격 판정** (30분)

🚨 **"돌아간다"가 아니라 "같은 답이 나온다"로 판정한다.**
8/14에 6000과 **소수점까지 일치** 9건(`r_guide_a_r` 0.991)을 확인해 뒀고 **그것이 기준선**이다.

```powershell
python bin_picking\src\run_binpick_e2e.py --npy <8/18 샘플> --no-web
```

| 확인 | 기준 |
|---|---|
| 검출 **개수** | 🚨 개수만 보면 안 된다(8/14) |
| ⭐ **부품 이름 + score** | **6000 결과와 대조** — 다르면 이식 오류 |
| `evaluator_sha256` | 6000과 **해시 일치**(8/21에 넣은 방어) |

🚨 **플래그를 빼면 조용히 틀린다** — `--real_uint16_max_depth_m` 누락 시
**검출이 늘면서 좌우가 뒤바뀌는데 무경고**였다(8/14). E2E 러너는 **검증된 플래그 6개를 코드에 못박아** 뒀다.

## 5. 🏭 금요일에만 되는 것 (원격 불가)

| # | 할 일 | 판정 |
|---|---|---|
| 1 | **Blaze 랜선 → IPC** | pylon으로 **실취득 1장** |
| 2 | **로봇 랜선 → IPC** | 소켓 왕복 1회 |
| 3 | 그리퍼 장착 | 개폐 |

🚨 **1번이 유일하게 OS 판단을 뒤집을 수 있는 지점**이다(8/14 기록).
⚠️ **카메라 네트워크는 맥에서 세 시간 걸렸다** — IPC는 Windows라 절차가 다르다.
**IP 대역 = 랜포트 대역** 원칙은 같다 → `memory/reference_dual_camera_setup_0824.md`

## ✅ 완료 기준

- [ ] RDP 접속 (잠금화면 상태 포함)
- [ ] `import` 6개 전부 OK
- [ ] `git pull` 최신
- [ ] ⭐ **npy 추론 결과가 6000과 부품 이름·score까지 일치**
- [ ] (금) Blaze 실취득 · 로봇 소켓 · 그리퍼 개폐

## 📌 막혔을 때 — 8/12·8/14에 실제로 막았던 것

| 증상 | 진짜 원인 |
|---|---|
| RDP 안 됨 | **토글을 켠 것 ≠ 서버가 리스닝** · `TermService`가 `Manual` |
| `ModuleNotFoundError` | **requirements.txt를 믿었다** — import 전수 추출로 확인 |
| `python`이 엉뚱한 것 실행 | **Store 앱 실행 별칭**이 가로챈다 |
| 스크립트 실행 거부 | **실행 정책** |
| ckpt가 로드는 되는데 값이 이상 | **파일이 깨졌다** — 🚨 `md5` 검증 필수 |
| ACCESS_DENIED | **관리자 창인지 확인 안 함**(3번 오독) |

⭐ **공통 형태 = "설정은 됐는데 다른 게 가로챈다"** — 8/12 TermService와 동형.
🚨 **결정적 정보는 읽으면 바로 나온다** — 로그·`Get-Service` 출력을 먼저 본다.
