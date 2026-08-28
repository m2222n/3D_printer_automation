# 🖥️ IPC-510 세팅 카드

## ✅✅ [2026-08-28 실행 완료] 이식 검증 통과 — 아래 실측 정정 4건

**결과** = E2E **5/5** · `compare_e2e_results` **"✅ 소수점까지 일치"** · **장당 1.33초**
⇒ 🎉 **KTR 3초 통과**(6000 4.3초 · A100 6.7초) · 상세 = `memory/project_ipc_e2e_verified_0828.md`

**🔬 이 카드에서 틀렸던 것 4개 (다음에 안 헤매게)**

| # | 카드 표기 | **실제** |
|---|---|---|
| 1 | (없음) | 🚨 **IPC에 git이 없었다** — `winget install --id Git.Git -e` 로 신설 설치. 설치 후 **새 창** 필요 |
| 2 | (없음) | 🚨 **venv 실경로 = `C:\binpick_venv`** (`C:\ipc_bundle\` 아래가 아니다) |
| 3 | *"**6000 → 맥 → IPC** 경로가 필요하다"* | ⭐ **불필요.** IPC에서 **`scp`로 6000을 당겨온다**(Windows에 OpenSSH·tar 내장) — *"6000이 못 보낸다"* 가 *"IPC가 못 가져온다"* 는 아니다 |
| 4 | 리포 없이 `mentoring_new` 만 | 🚨 **E2E 러너는 리포 안에 있다** ⇒ `git clone`(HTTPS+브라우저 로그인, SSH 키 없음) |

```powershell
# 3번 실제 명령
scp -P 5533 jtm@<6000_IP>:/data/jtm/ipc_transfer_0828.tar.gz C:\ipc_bundle\
cd C:\ipc_bundle ; tar -xzf ipc_transfer_0828.tar.gz
```

**🚨 여기서 나온 새 버그 = cp949** — Windows 한글판에서 **이모지가 E2E를 죽였다**(5/5 실패).
✅ 커밋 `bb38c59`·`78fa534` 로 **근본 수정 완료**(15곳 + `utils/console_utf8.py`) ⇒
**지금은 환경변수 없이 그냥 돌아간다.** 회귀 = `python bin_picking\tests\test_console_utf8.py` **11/11**

**🟡 남은 것** = `angle=0.0`(마스크 미저장 · **다음 재택**) · numpy가 **1.26.4→2.5.2**, opencv **4.11→5.0** 으로 바뀜(결과는 동일했으나 이상 시 첫 의심 대상)

---

<details>
<summary>⛔ 이하 8/26 작성 원본 (이력 · 절차는 유효)</summary>

# 원본 — 8/26(화) 재택 오전

> 🎯 **목표** = 금요일(8/29)에 IPC에서 **로봇 + 카메라 + 인식**이 한 자리에서 돌게 만든다.
> 🚨 **이것이 hand-eye의 선행조건**이다 — 로봇은 지금 공장 PC에 붙어 있고 배포 대상은 IPC다.
> 공장 PC에서 먼저 하면 **나중에 IPC에서 다시 해야 한다.**
>
> ⚠️ **원격으로 되는 것과 안 되는 것을 갈라놨다.** 오전에 원격분을 끝내면
> 금요일엔 **케이블만 옮겨 확인**하면 된다.

## 0. 접속 (10분)

```
🔒 접속 정보(Tailscale IP · tailnet · RDP 계정/비번)
   = memory/reference_dev_environment.md · memory/project_ipc510_remote_access_0812.md
   🚨 이 파일은 git 추적 대상이라 여기 적지 않는다(개인 repo가 한솔 미러로 나간다)
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

## 2. 새로 필요한 것 (20분)

### 🔬 8/25 재실측 — **E2E 러너 의존성은 5개, 전부 확인했다**

`run_binpick_e2e.py`는 **`subprocess`로 추론기를 부른다**(6000에 torch가 없어도 되게 한
설계). 그래서 **러너 파일만 보면 의존성이 안 나온다** — subprocess 대상까지 따라가야 한다.
AST로 **리포 내부 13개 파일**을 재귀 추적해 뽑은 실제 외부 패키지:

| 패키지 | 어디서 | IPC 상태 |
|---|---|---|
| `numpy` | 11개 파일(전처리·모델·후처리·게이트·6요소) | 🟢 8/14 설치(1.26.4) |
| `torch` | `infer`·`model`·`postprocess`·`geometry`·`depth_preprocess` | 🟢 8/14 설치(+cpu) |
| `PIL` | `depth_preprocess`·`real_labelme`·`visualization` | 🟢 8/14 설치 |
| **`cv2`** | `rgbd_fusion` | 🔴 **설치 필요** |
| **`yaml`** | `input_gate` | 🔴 **설치 필요** |

```powershell
pip install opencv-python pyyaml
```

🚨 **`pypylon`은 E2E 의존성이 아니다** — 카메라 실취득 전용이라 §5(금요일)에서만 쓴다.
카드 이전 판이 3개를 한 줄에 묶어둬서 갈랐다.

⚠️ `blenderproc`·`bpy`·`trimesh`·`h5py`·`pyrender`·`matplotlib`·`skimage`는
**합성 데이터 생성용**이라 IPC에 불필요하다.

### 🚨 체크포인트가 리포에 없다 — 따로 넣어야 한다

`T100_best.pt`는 **git에 없다**(70MB). 러너 기본 경로는
`bin_picking/models/T100_best.pt`이고, 6000 원본은
`/data/jtm/a100_backup_0710/checkpoints/extracted/runs/T100_csblur_lr1e4_ep80/best.pt`.

| 항목 | 값(8/25 실측) |
|---|---|
| **md5** | `afcf73511be501ebd813a08bd91a1b65` |
| 크기 | 70,008,856 bytes |
| 신원 | `input_mode=zv` · lr 1e-4 · ep80 · batch 2 · amp False · **첫 conv (32,2,3,3)** |

🚨 **IPC에 넣은 뒤 md5를 반드시 대조한다** — *"ckpt가 로드는 되는데 값이 이상"* 은
파일 손상이 원인인 알려진 유형이다(§막혔을 때 표).

## 3. 코드 최신화 (10분)

```powershell
git pull        # origin/main = 60cdc00 이후 (8/24 push 완료)
```
🚨 **8/24 교훈** — 6000에서 만든 것은 **push 안 하면 다른 데서 안 보인다.**
지금은 push돼 있으니 pull로 최신이 온다.

## 4. ⭐⭐ 결과 대조 = **이 세팅의 합격 판정** (30분)

🚨 **"돌아간다"가 아니라 "같은 답이 나온다"로 판정한다.**

### ✅ 정답표를 8/25에 미리 만들어 뒀다 (이전 판에는 "대조하라"만 있고 대조 대상이 없었다)

```
6000 기준선 = /data/jtm/e2e_reference_0825/
   six/shot_00{1..5}_c1.six.json   ← 정답값 5장
   env.json                        ← 환경 지문
```

**8/25 6000 실측 결과** (`T100_best.pt` · thr 0.20 · 화이트리스트 적용):

| shot | 검출 | 주요 부품 | 게이트 |
|---|---|---|---|
| 001 | **7** | `09_guide_paper_r`, `07_guide_paper_l`, `13_x2_bcf8ccb4`, `brkt_switch` | in_distribution 3.13% |
| 002 | **7** | `09_guide_paper_r`, `brkt_switch`, `bracket_sensor1`, `07_guide_paper_l` | 2.64% |
| 003 | **7** | `13_x2_bcf8ccb4`, `14_13`, `bracket_sensor1`, `r_guide_a_r` | 3.39% |
| 004 | **8** | `09_guide_paper_r`, `07_guide_paper_l`, `brkt_switch`, `14_13` | 2.63% |
| 005 | **6** | `14_13`, `r_guide_a_r`, `bracket_sensor1`, `07_guide_paper_l` | 2.73% · **제외종 −1** |

⭐ shot_005에서 **화이트리스트가 실제로 1건을 걸러낸다**(`17_mks_holder`) — 이것까지 재현돼야 한다.

### 🅰️ IPC에서 실행

```powershell
# 기준선과 **완전히 같은 명령**
python bin_picking\src\run_binpick_e2e.py ^
  --depth-dir <8/18 npy 폴더> --glob "shot_00[1-5]_c1.npy" ^
  --out-dir ipc5

# 환경 지문
python bin_picking\depth_track\scripts\emit_env_fingerprint.py --out ipc5\env.json
```

### 🅱️ 자동 대조 — 사람이 눈으로 비교하지 않는다

```powershell
python bin_picking\depth_track\scripts\compare_e2e_results.py ^
  --ref <6000에서 받은 e2e_reference_0825> --test ipc5
```

**무엇을 보나** (엄격한 순서):

| # | 항목 | 허용 |
|---|---|---|
| ① | 장면 수 · 검출 개수 | 정확히 일치 |
| ② | ⭐ **부품 이름 집합** | 정확히 일치 — **좌우 뒤바뀜을 여기서 잡는다** |
| ③ | ⭐ **`confidence`·`cad_score`** | **1e-4** (같은 가중치면 비트 단위로 같아야) |
| ④ | 좌표 `x,y,z` | **0.5mm** (1px≈1.45mm의 1/3) |
| ⑤ | 게이트 `verdict`·`trusted`·유효율 | 일치 |
| ⑥ | 환경 지문 (torch·numpy·ckpt md5·코드 sha256) | 다르면 표시 |

### ✅ 이 대조 도구는 **작동을 검증했다** (8/25)

🚨 **8/14 사고를 실제로 재현해서 잡히는지 확인**했다 —
`--real_uint16_max_depth_m`를 빼고 돌리니 **검출 7건 → 1건**이 되었고, 도구가:

```
🔴 shot_001_c1
     검출 개수 1 ≠ 기준 7
     🚨기준에만 있는 부품 {'09_guide_paper_r': 1, '07_guide_paper_l': 1, ...}
     🚨테스트에만 있는 부품 {'02_sol_block_b': 1}
     🚨🚨 '09_guide_paper_r' — 좌우 접미사 부품이 어긋났다. 8/14에 정확히 이 증상
     게이트 제외 1건 {'17_mks_holder': 1} ≠ 기준 0건
🔴 이식 검증 실패 — 이 상태로 로봇에 연결하지 말 것
```

⭐ **동일 입력끼리는 통과**하고 **어긋난 입력은 거부**한다 — 양쪽을 다 봤다.

🚨 **플래그를 빼면 조용히 틀린다** — E2E 러너는 **검증된 플래그 6개를 코드에 못박아** 뒀으니
**러너를 쓰고 추론기를 직접 부르지 않는다.**

## 5. 🏭 금요일에만 되는 것 (원격 불가)

| # | 할 일 | 판정 |
|---|---|---|
| 1 | **Blaze 랜선 → IPC** | pylon으로 **실취득 1장** |
| 2 | **로봇 랜선 → IPC** | 소켓 왕복 1회 |
| 3 | 그리퍼 장착 | 개폐 |

🚨 **1번이 유일하게 OS 판단을 뒤집을 수 있는 지점**이다(8/14 기록).
⚠️ **카메라 네트워크는 맥에서 세 시간 걸렸다** — IPC는 Windows라 절차가 다르다.
**IP 대역 = 랜포트 대역** 원칙은 같다 → `memory/reference_dual_camera_setup_0824.md`

## 6. 📦 6000 → IPC 로 옮길 것 (git에 없는 것들)

| 항목 | 6000 경로 | 크기 |
|---|---|---|
| **체크포인트** | `/data/jtm/a100_backup_0710/checkpoints/extracted/runs/T100_csblur_lr1e4_ep80/best.pt` | 70MB |
| **대조 기준선** | `/data/jtm/e2e_reference_0825/` | 80KB |
| **테스트 npy** | `/data/jtm/synth_out/blaze_capture_0818/shot_00{1..5}_c1.npy` | ~5MB |

⚠️ **6000 → 맥 → IPC** 경로가 필요하다(6000에 Tailscale이 없어 IPC로 직접 못 보낸다).
🚨 사무실 Wi-Fi는 **AP isolation**이라 맥→6000이 막힐 수 있다(7/16 확인).

## ✅ 완료 기준

- [ ] RDP 접속 (잠금화면 상태 포함)
- [ ] `import` **5개**(`numpy`·`torch`·`PIL`·`cv2`·`yaml`) 전부 OK
- [ ] `git pull` 최신
- [ ] **ckpt md5 = `afcf73511be501ebd813a08bd91a1b65`** 대조
- [ ] ⭐⭐ **`compare_e2e_results.py`가 "✅ 소수점까지 일치" 출력**
      (부품 이름·score·좌표·게이트까지 — 개수만 보지 않는다)
- [ ] (금) Blaze 실취득 · 로봇 소켓 · 그리퍼 개폐

## 📊 참고 = 6000 실측 지연 (KTR 3초 대비)

8/25 6000(CPU) 실측 = **장당 4.27~4.57초**. 8/21 A100 기록은 6.7~7.5초였다.
🚨 **원인은 추론이 아니라 매번 모델을 다시 로드하는 것**(러너가 subprocess로 띄운다)
⇒ ⭐ **상주 프로세스가 해법**이고, IPC는 **RTX 5060이 있어 더 빠를 수 있다**.
📌 **[미확인]** IPC torch가 `+cpu` 빌드라 GPU를 안 쓴다 — GPU를 쓰려면 CUDA 빌드 재설치가 필요하다.
   지금은 **되는 것이 먼저**이고(8/14 원칙) 속도는 그 다음이다.

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

</details>
