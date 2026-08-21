# IPC-510 빈피킹 실행환경 세팅 (2026-08-14)

> **목표** = IPC에서 **npy 1장 넣어 검출이 나오는 것**까지. 그 이상은 다음.
> ⭐ 8/5 산출물(모듈 3개)이 **여기서 돌아야** 하므로 이 환경이 배포 대상이다.
>
> ⭐ **원격이 열려 있어 재택에서도 된다**(8/12 Tailscale+RDP) → 공장 시간을 여기 쓰지 말 것.

---

## 0. 접속

맥 **Windows App** → PC name **`<IPC_TAILSCALE_IP>`** → `<계정>` + 비번

📌 **실제 접속값은 리포에 두지 않는다** — `memory/project_ipc510_remote_access_0812.md`(비공개) 참조.

🚨 **PC가 켜져 있어야 한다.** 꺼졌으면 전원만 넣으면 된다
(**HDMI는 GPU 포트 그대로** — 백패널로 옮기면 화면이 사라진다).

---

## 1. 확정된 IPC 사양 (8/12 dxdiag 실측)

| 항목 | 값 | 뜻 |
|---|---|---|
| CPU | **i7-14700** (20C/28T) | ✅ **10초 예산 리스크 해소**(6000보다 느리지 않다) |
| GPU | **RTX 5060 8GB** (드라이버 32.0.15.8180) | ⭐ GPU 추론 여지. **단 1차 목표는 CPU** |
| RAM | 32GB | 충분 |
| OS | **Win11 IoT Enterprise 25H2** (b26200) | |

⭐ **CPU부터 하는 이유** = 6000에서 **검증된 조합**이 CPU이고(100장 5분),
GPU는 CUDA 빌드·드라이버 정합이라는 **새 변수**를 들인다.
**되는 것을 먼저 만들고, 빨라지는 것은 그 다음이다.**

---

## 2. 설치

### 2-1. Python 3.12

⚠️ **IPC는 깡통이었다** — Python 없음(8/14 확인). 인터넷은 됨(pypi 7ms).

🚨 **먼저 Microsoft Store 앱 실행 별칭을 끌 것.** 안 끄면 `python`이
**Store 껍데기로 가로채져** 설치해도 안 잡힐 수 있다:
```powershell
start ms-settings:advanced-apps
```
→ **앱 실행 별칭** → `python.exe`·`python3.exe` **둘 다 끄기**

그다음 [python.org 3.12.8](https://www.python.org/downloads/release/python-3128/)
→ **Windows installer (64-bit)** → 🚨 **"Add python.exe to PATH" 체크**(기본 꺼짐)
+ 설치 끝 화면의 **"Disable path length limit"** 눌러두면 좋다(260자 제한 해제).

🔴 **반드시 새 PowerShell 창**에서 확인(PATH는 기존 창에 반영 안 됨):
```powershell
python --version
```
```powershell
where.exe python
```
**기대**: `Python 3.12.8` / `C:\Users\<계정>\AppData\Local\Programs\Python\Python312\python.exe`
🚨 `WindowsApps`가 나오면 별칭이 안 꺼진 것.

### 2-2. 패키지 (⭐ 6000에서 검증된 조합)

🔴 **PowerShell은 여러 줄 붙여넣기를 경고한다 → 한 줄씩 실행할 것.**

```powershell
python -m venv C:\binpick_venv
```
```powershell
C:\binpick_venv\Scripts\Activate.ps1
```
🚨 **활성화가 실행 정책에 막히면**(8/14 실제로 막혔다):
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
⭐ **재부팅 후에도 되게 하려면 한 번만**:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
📌 이때 *"업데이트했지만 재정의되었습니다"* 경고가 뜨는데 **실패가 아니다** —
CurrentUser엔 저장됐고 현재 창만 Process(Bypass)가 우선하는 것이다.
⭐ **활성화가 끝내 안 되면 그냥 전체 경로로 불러도 된다**(`C:\binpick_venv\Scripts\pip.exe`).
venv는 프롬프트 표시가 목적이 아니라 그 안의 python/pip을 쓰는 것이 목적이다.

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```
```powershell
pip install numpy==1.26.4 tqdm pillow scipy
```

🚨 **numpy는 반드시 1.26.4** — 2.x는 A100 환경에서 깨진 전례가 있다(7/8 컨테이너 재생성 때 복구).

🚨🚨 **`pillow`·`scipy`를 빼먹지 말 것** — 8/14에 실제로 여기서 막혔다
(`ModuleNotFoundError: No module named 'PIL'`).
`mentoring_new/requirements.txt`에는 **numpy·torch·tqdm만** 적혀 있는데
**실제 import는 PIL·scipy가 더 있다**(`depth_vq_detector/depth_preprocess.py:10`).
⇒ ⭐⭐ **requirements.txt를 믿지 말고 import를 전수로 뽑을 것**:
```bash
grep -rhoE "^\s*(import|from)\s+[a-zA-Z_][a-zA-Z0-9_]*" depth_vq_detector/*.py infer_depth_vq_detector.py | sort -u
```
📌 **"파일을 읽은 것"과 "그게 진짜 의존성인지 확인한 것"은 다른 문제다**
— 시그니처 추측 금지와 같은 계열.
⭐ 다만 이건 `ModuleNotFoundError`로 **크게 실패**해서 즉시 잡혔다(좋은 실패).

```powershell
python -c "import torch,numpy;print(torch.__version__,numpy.__version__)"
# 기대: 2.x.x+cpu 1.26.4
```

### 2-3. 🎁 번들 전송 (코드 + 모델 + 샘플 = 한 파일)

⭐ **git clone을 쓰지 않는다** — 사설 리포라 IPC에서 인증 설정이 필요하고,
오늘 목적(추론 1장)엔 **코드 2MB + 모델 67MB면 충분**하다.

**6000에 준비돼 있음**: `ipc_binpick_bundle_0814.tar.gz` (**62MB**)
```
ipc_bundle/
  mentoring_new/   ← 추론 코드 (depth_vq_detector 포함, 2MB)
  models/T100_best.pt   ← ⭐ 배포 모델 (67MB)
  sample/shot_001_g1.npy ← 검증용 실촬영 1장
```

**전송** (6000 → 맥 → IPC):
```bash
# 6000 → 맥 (맥 터미널에서)
scp <6000>:<번들경로>/ipc_binpick_bundle_0814.tar.gz ~/Desktop/
```
그 다음 **RDP 창에 드래그&드롭**하거나, 맥에서 IPC로 직접 scp.
📌 RDP 클립보드 파일 복사가 가장 간단하다.

**IPC에서 압축 해제** (PowerShell):
```powershell
cd C:\
tar -xzf $env:USERPROFILE\Desktop\ipc_binpick_bundle_0814.tar.gz
# → C:\ipc_bundle\ 생성
```
⭐ Win11엔 `tar`가 기본 내장이라 별도 설치가 필요 없다.

**🔴 전송 검증 — 반드시 할 것**:
```powershell
Get-FileHash C:\ipc_bundle\models\T100_best.pt -Algorithm MD5
# 기대: AFCF73511BE501EBD813A08BD91A1B65
```
🚨 **한 글자라도 다르면 전송이 깨진 것**이다. 다시 옮길 것 —
깨진 체크포인트는 **로드는 되면서 엉뚱한 값**을 낼 수 있다.

⭐ **T100이 현재 배포 모델**이다. 8/7 재학습(`c1plus_0806_best.pt`)은
**holdout F1 0.4231→0.2917로 하락해 배포하지 않았다.**
🚨 **c1plus를 실수로 쓰지 말 것.**

---

## 3. ✅ 검증 — 이 명령이 정답이다 (6000에서 실측 확인)

```powershell
C:\binpick_venv\Scripts\activate
cd C:\ipc_bundle\mentoring_new

python infer_depth_vq_detector.py `
  --checkpoint ..\models\T100_best.pt `
  --depth ..\sample\shot_001_g1.npy `
  --real_uint16_max_depth_m 10.0 `
  --score_thresh 0.20 --mask_thresh 0.5 `
  --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" `
  --out_dir C:\binpick_out\smoke
```

**기대 = `Saved 9 predictions` 이상** (⭐ **thr 0.20에서는 9건보다 많이 나온다**)

> ⭐⭐ **2026-08-21 갱신 = `--score_thresh` 0.45 → 0.20**
> 8/18 90장 스윕에서 0.20이 최적점(F1 0.5445→**0.5838**). 🚨판정 근거는 F1이 아니라
> **집을 수 있는 부품 491→577개**(GT 대비 77.9%→**91.6%**, 추가 치명은 +9뿐 = 9.6:1).
> 🚨 **그래서 "9건"은 더 이상 합격 기준이 아니다** — 아래 이름·score 대조가 기준이다.
> 📌 옛 기준선(0.45에서 9건·`r_guide_a_r` 0.991)은 **thr을 0.45로 주면 재현된다**.

### 🔴 개수만 보지 말 것 — 부품 이름까지 대조

```powershell
python -c "import json;p=json.load(open(r'C:\binpick_out\smoke\predictions.json'));p=p.get('predictions',p);print(len(p));[print(' ',x['cad_id'],round(x['score'],3)) for x in p[:3]]"
```

**6000에서 이 번들을 그대로 돌린 정답** (2026-08-14 실측):
```
9
  r_guide_a_r__82d6ea93        0.991
  03_sol_block_front__b991ec0d 0.883
  13_variant__105573ee         0.853
```

⭐ **세 줄이 다 맞으면 IPC 추론 환경이 6000과 동일하다** = 오늘의 성공 기준.
🚨 개수만 9로 맞고 이름·score가 다르면 **환경이 다른 것**이다(아래 참조).

---

## 🚨🚨 플래그를 빼면 조용히 틀린다 — 8/14 실측으로 확인

**같은 파일·같은 체크포인트인데 플래그만 빼면 결과가 통째로 달라진다:**

| 실행 | 검출 수 | 1위 검출 | 2위 검출 |
|---|---|---|---|
| ✅ **플래그 있음**(위 명령) | **9건** | `r_guide_a_**r**` 0.991 | `03_sol_block_front` 0.883 |
| ❌ 플래그 없음 | 10건 | `r_guide_a_**l**` 0.911 | `bracket_case` 0.910 |

⭐⭐ **개수만 다른 게 아니라 "어느 부품인가"가 다르다.**
좌우(`_l`/`_r`)가 뒤바뀌고 부품 종류 자체가 달라지는데,
🚨 **에러도 경고도 없이 그럴싸한 값이 나온다.**

**왜** = `--real_uint16_max_depth_m` 기본값이 `None`이라
**raw uint16을 mm로 취급**한다(실제는 `raw×10/65535 = m`).
그러면 z가 6~7배로 뻥튀기돼 `--depth_keep_range 0.40,0.60`에서 부품이 엉뚱하게 걸러진다.

📌 **이건 7/30에 이미 겪은 버그다** — 같은 플래그 누락으로 검출이 9건→2건이 됐고,
그때 *"못 잡았으면 cross-session 폭락으로 오진했을 것"*이라고 적었다.
**닷새에 다섯 번 밟은 depth 단위 버그와 같은 계열**이고, 전부 "조용히 그럴싸한 값"이었다.

⇒ ⭐ **IPC에서 검출 수만 보고 "된다"고 판단하지 말 것.**
**부품 이름과 score를 6000 결과와 대조**해야 진짜 같은 값인지 안다.

---

---

## ✅ 8/14 실행 결과 — 완료

**IPC 실측 출력이 6000과 소수점까지 일치**:
```
9
  r_guide_a_r__82d6ea93        0.991
  03_sol_block_front__b991ec0d 0.883
  13_variant__105573ee         0.853
```
⇒ ⭐ **IPC-510에서 빈피킹 인식이 실제로 돈다.** 8/5 산출물 3개 중 ①이 배포 하드웨어에서 검증됨.

**소요** = 약 1시간(설치 대기 포함). **막힌 지점 3개**(전부 위에 반영):
① Store 앱 실행 별칭 ② venv 활성화 실행 정책 ③ **PIL·scipy 누락**

⭐ **개수만 보지 않은 것이 핵심이었다** — 플래그를 뺀 오실행이 **10건·`r_guide_a_l` 0.911**로
그럴싸하게 나왔기 때문에, 이름·score까지 대조하지 않았으면 좌우가 뒤바뀐 것을 못 잡았다.

📌 **전송은 IPC에서 직접 scp가 정답**(RDP 드래그&드롭은 막혀 있었다).
호스트 키 지문은 6000에서 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`로 대조 후 `yes`.

---

## 4. 다음 (오늘 아님)

- [ ] web-api를 IPC에서 기동 → `POST /api/v1/binpick/reports` 왕복
      (🔴 **8/13 라우터는 서버 재시작이 필요**하다 — 지금 도는 프로세스는 `/binpick/*` 미서빙)
- [ ] Blaze 촬영 → 추론 → 웹 보고까지 E2E
- [ ] pylon 설치(카메라를 IPC에 물릴 때)
- [ ] 서비스 등록(NSSM 등) — 무인 재시작

---

## 관련
- `memory/project_ipc510_remote_access_0812.md` — 접속값·원격 유지 조건
- `memory/project_crosssession_retrain_0806.md` — c1plus를 안 쓰는 이유
- `memory/feedback_verify_units_and_signatures.md` — depth 단위 버그 이력
- `bin_picking/depth_track/scripts/detect_nolabel.py:97` — 실촬영 플래그 원본
