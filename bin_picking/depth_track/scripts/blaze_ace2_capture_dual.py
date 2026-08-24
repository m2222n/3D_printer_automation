#!/usr/bin/env python3
"""
Blaze(depth) + ACE2(RGB) **동시 촬영** — 맥북에서 실행. (2026-08-24 신설)

⭐ 왜 만들었나
------------------------------------------------------------
현재 인식은 **depth 단독**이고 남은 병목이 **종류 식별(61.3%)** 이다.
부품이 회색 단색이라 형상이 비슷한 것끼리 안 갈리는 것이 원인이고,
**RGB를 같이 넣는 것**이 그 해법 후보다(= 궁극 목표의 D단계).

🚨 그런데 **RGB 실측 데이터가 0건**이다(8/21 전수 확인).
   8/18 90장은 `.npy` = (480,848) uint16 **depth 단독**이고,
   같이 있는 `.png`는 **depth 컬러맵 렌더**(1696×960 = npy의 2배)라
   카메라 컬러가 아니다.
⇒ 그래서 D단계는 "모델에 RGB를 붙이는 일"이 아니라 **데이터를 만드는 일**부터고,
  그건 공장에서만 된다. **이 스크립트가 그 일을 한다.**

🚨🚨 그리고 후처리로는 못 끝낸다 (8/24 체크포인트 직접 확인)
------------------------------------------------------------
    T100_csblur_lr1e4_ep80/best.pt
      input_mode = zv
      backbone.stem.0.block.0.weight = (32, 2, 3, 3)  ← 입력 2채널로 물리적으로 박힘

RGB를 넣으면 첫 conv shape이 바뀌어 **기존 체크포인트를 못 읽는다 = 재학습 필수.**
8/21 화이트리스트처럼 후처리로 이득을 얻는 경로가 아니다.

⭐⭐ 그래서 **세션을 2회차로 나눈다** (이 스크립트의 핵심 설계)
------------------------------------------------------------
재학습이 필수면 **오늘 찍은 것은 학습셋**이 된다. 그것으로 성능을 재면
8/20에 밟을 뻔한 **train-on-test**를 그대로 반복하게 된다.

    세션 A (오전)      60장  → 🎓 학습셋
    세션 B (오후·재설치) 30장  → 🧪 시험지 (이걸로만 판정)

`--session A` / `--session B`로 지정하면 파일명·메타에 박힌다.
🚨 **B는 학습에 절대 넣지 않는다.**

무엇을 고정하나 (⭐ 원인 분리)
------------------------------------------------------------
depth 쪽 설정·판정은 **8/18 90장을 성공시킨 `blaze_capture_crosssession.py`와 동일**하게
가져왔다(ShortRange 강제 · 필터 On · KEEP_RANGE 400~600 · center_crop 1/6~5/6 ·
BAND 8000px 판정 · raw uint16 저장). **바뀐 것은 ACE2가 추가된 것뿐**이다.

  이유: depth 조건이 바뀌면 8/18과 비교가 안 되고, RGB가 이득인지
        조건이 달라진 탓인지 구분할 수 없다.

저장물 (한 번 누르면 3개 + 메타)
------------------------------------------------------------
    shot_NNN_cC_sA.npy      Blaze raw uint16 (480,848)  ← 학습셋과 동일 포맷
    shot_NNN_cC_sA_rgb.png  ACE2 컬러 원본 (BGR, 무손실)  ← 🆕 이번에 얻으려는 것
    shot_NNN_cC_sA.png      depth 컬러맵 미리보기(판정용)
    capture_meta.json       장별 품질 + RGB 상태

🚨 RGB는 **원본 해상도 그대로** 저장한다(리사이즈·JPEG 금지).
   정렬(D-1)은 재택에서 extrinsic으로 하고, 그때 원본이 있어야 한다.

키
------------------------------------------------------------
  s     = 저장   스페이스 = 조건 변경   u = 직전 취소   q/ESC = 종료

실행
------------------------------------------------------------
  # 0) 카메라 네트워크 (어댑터 꽂은 뒤 한 줄) — 🚨 반드시 먼저
  sudo python bin_picking/tests/setup_camera_net.py --apply

  # 1) 오전 = 학습셋 60장
  sudo python blaze_ace2_capture_dual.py --session A --target 60 \
       --out ~/Desktop/dual_capture_0824

  # 2) 오후 = 카메라 한 번 떼었다 다시 달고 시험지 30장
  sudo python blaze_ace2_capture_dual.py --session B --target 30 \
       --out ~/Desktop/dual_capture_0824

  # 3) 전송
  scp -r ~/Desktop/dual_capture_0824 <6000>:/data/jtm/
"""
from __future__ import annotations
import argparse, os, sys, time, glob, re, json
import numpy as np

try:
    from pypylon import pylon
    import cv2
except Exception as e:
    sys.exit("pypylon/opencv import 실패: %s\n맥북 binpick venv에서 실행하세요." % e)


# ============================================================
# 학습셋과 반드시 일치시켜야 하는 상수 (건드리지 말 것)
#   출처: blaze_capture_crosssession.py:79-82 — 8/18 90장이 이 값으로 찍혔다
# ============================================================
# 근거: reproduce_f1_0684.sh:54 --depth_keep_range '0.40,0.60'
KEEP_RANGE_MM = (400, 600)
# 근거: reproduce_f1_0684.sh:53 --center_crop '1/6,5/6'
CENTER_CROP = (1 / 6, 5 / 6)
# 근거: blaze_capture_crosssession.py:333 — 학습셋 실측(부품 px 10k+)의 crop 환산
BAND_PX_MIN = 5000   # 8/24 현장 보정: 8000은 8/18 통과분(4%≈7k)도 떨어뜨렸다


def _try(label, fn):
    try:
        fn(); print(f"  ✓ {label}"); return True
    except Exception as e:
        print(f"  · {label} 건너뜀 ({type(e).__name__})"); return False


# ============================================================
# 카메라 개방 — 🟢 7/28 extrinsic 캘리브에서 검증된 방식 그대로
#   출처: tests/verify_rgbd_overlay.py:65-103
#        = tests/calibrate_blaze_ace2_extrinsic.py:82-126 (동일 함수)
# ============================================================
def open_cam(ip: str, throughput_mbps: float = 20.0):
    """IP로 카메라를 연다. **두 카메라 동시 개방에 쓰인 검증된 경로.**

    ⚠️ macOS + 다중 어댑터(en8/en10 서로 다른 서브넷)에서는 IP 직접
       CreateDevice가 'Failed to discover'로 실패한다. GigE TL의
       EnumerateAllDevices로 먼저 링크를 스캔한 뒤 IP 매칭되는 device로
       여는 방식이 견고하다. (7/28 현장에서 확립)

    🚨 throughput 기본값을 20Mbps로 낮춰 잡았다 (원본은 30).
       ACE2 5MP(6.5MB/frame)와 Blaze를 **동시에** 물리는 것은 처음이라
       30이 검증된 값이 아니다. 깨지면 --throughput 15 → 10으로 낮춘다.
    """
    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")
    target = None
    try:
        for d in gige.EnumerateAllDevices():
            if d.IsIpAddressAvailable() and d.GetIpAddress() == ip:
                target = d
                break
    except Exception:
        target = None
    if target is None:
        target = pylon.DeviceInfo()
        target.SetIpAddress(ip)
        target.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(target))
    cam.Open()
    for name, val in (("GevSCPSPacketSize", 1500),):
        try:
            cam.GetNodeMap().GetNode(name).SetValue(val)
        except Exception:
            pass
    try:
        n = cam.GetNodeMap().GetNode("GevSCPD")
        if n is not None:
            n.SetValue(min(1000, int(n.Max)))   # Blaze는 Max가 96이라 클램프됨
    except Exception:
        pass
    try:
        n = cam.GetNodeMap().GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            lim = int(throughput_mbps * 1_000_000)
            n.SetValue(max(int(n.Min), min(lim, int(n.Max))))
    except Exception:
        pass
    try:
        cam.MaxNumBuffer.SetValue(30)
    except Exception:
        pass
    return cam


def _autodiscover(model_kw: str) -> str | None:
    """모델명으로 IP를 찾는다. 열거는 브로드캐스트라 대역이 어긋나도 보인다.

    ⚠️ 단 **열기는 유니캐스트**라 대역이 맞아야 한다 → [[gige-camera-network-rule]]
       즉 "보이는데 안 열림"이면 대역 문제지 카메라 문제가 아니다.
    """
    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")
    found = []
    for d in gige.EnumerateAllDevices():
        try:
            name = d.GetModelName() or ""
            ip = d.GetIpAddress() if d.IsIpAddressAvailable() else None
        except Exception:
            continue
        if model_kw.lower() in name.lower() and ip:
            found.append((name, ip))
    if not found:
        return None
    name, ip = found[0]
    print(f"🔎 {model_kw} 자동 발견: {name} @ {ip}")
    if len(found) > 1:
        print(f"   ⚠️ {len(found)}대 보입니다. 첫 번째를 씁니다 — 다르면 IP로 직접 지정하세요.")
    return ip


def setup_blaze(cam):
    """depth 설정 — 🚨 8/18과 **완전히 동일**해야 한다.

    출처: blaze_capture_crosssession.py:128-168 그대로.
    """
    try:
        cam.ComponentSelector.SetValue("Intensity"); cam.ComponentEnable.SetValue(False)
    except Exception as e:
        print("Intensity off 경고:", e)
    try:
        cam.ComponentSelector.SetValue("Range"); cam.ComponentEnable.SetValue(True)
        try: cam.PixelFormat.SetValue("Coord3D_C16")
        except Exception: cam.PixelFormat.SetValue("Mono16")
    except Exception as e:
        print("Range 설정 경고:", e)
    print("Blaze 연결:", cam.GetDeviceInfo().GetModelName(), cam.GetDeviceInfo().GetIpAddress())

    print("[depth 품질 파라미터 — 8/18 학습셋과 동일하게 고정]")
    # 🔴 ShortRange는 경고가 아니라 **종료** 사유 (7/30 격상, 8/18에도 유지)
    #    7/6에 LongRange로 찍혀 품질저하가 발생했고, 조용히 잘못 찍히면 하루가 날아간다.
    ok = _try("OperatingMode=ShortRange", lambda: cam.OperatingMode.SetValue("ShortRange"))
    try:
        cur = cam.OperatingMode.GetValue()
        if cur == "ShortRange":
            print(f"  ✅ OperatingMode = {cur} (8/18과 일치)")
        else:
            cam.Close()
            sys.exit(
                f"\n🔴🔴 중단: OperatingMode = {cur} (ShortRange 아님, set성공={ok})\n"
                "   8/18 90장이 ShortRange라 이대로 찍으면 RGB 이득인지\n"
                "   설정 불일치인지 구분할 수 없습니다.\n"
                "   → pylon Viewer에서 OperatingMode 확인 후 재시도."
            )
    except SystemExit:
        raise
    except Exception as e:
        print(f"  ⚠️ OperatingMode 재확인 실패: {e} — 계속하려면 확인 필요")

    for node in ("SpatialFilter", "Scan3dSpatialFilter"):
        if _try(f"{node}=On", lambda n=node: getattr(cam, n).SetValue(True)): break
    for node in ("TemporalFilter", "Scan3dTemporalFilter"):
        if _try(f"{node}=On", lambda n=node: getattr(cam, n).SetValue(True)): break
    for node in ("OutlierRemoval", "Scan3dOutlierRemoval", "FlyingPixelsRemoval"):
        if _try(f"{node}=On", lambda n=node: getattr(cam, n).SetValue(True)): break


def setup_ace2(cam, exposure_us: float | None = None):
    """ACE2 노출.

    ⚠️ 7/29 교훈: 캘리브 때 쓴 짧은 노출(3ms)이 카메라에 남아 있으면 실내에서
       **화면이 거의 검게** 나온다. 캘리브와 촬영은 요구가 반대다.
    ⭐ 기본은 auto — 부품을 휘저으며 찍으므로 장면이 계속 바뀐다.

    출처: tests/verify_rgbd_overlay.py:106-144
    """
    nm = cam.GetNodeMap()

    def _set(name, val):
        try:
            n = nm.GetNode(name)
            if n is not None:
                n.SetValue(val); return True
        except Exception:
            pass
        return False

    # 픽셀 포맷: 컬러를 원한다 — BGR8이 되면 변환이 불필요하다
    fmt = None
    for cand in ("BayerRG8", "BGR8", "RGB8"):
        if _set("PixelFormat", cand):
            fmt = cand; break
    if fmt is None:
        print("  ⚠️ PixelFormat 설정 실패 — 카메라 현재 포맷을 그대로 씁니다")
    else:
        print(f"  ✓ ACE2 PixelFormat = {fmt}")

    if exposure_us is not None:
        _set("ExposureAuto", "Off")
        for name in ("ExposureTime", "ExposureTimeAbs"):
            try:
                n = nm.GetNode(name)
                if n is not None:
                    v = max(float(n.Min), min(float(exposure_us), float(n.Max)))
                    n.SetValue(v); print(f"  ✓ ACE2 노출 고정 {v/1000:.1f}ms"); break
            except Exception:
                continue
    else:
        ok = _set("ExposureAuto", "Continuous") or _set("ExposureAuto", "Once")
        _set("GainAuto", "Continuous") or _set("GainAuto", "Once")
        print(f"  ✓ ACE2 노출 auto" if ok else "  ⚠️ ACE2 노출 auto 실패")

    print("ACE2 연결:", cam.GetDeviceInfo().GetModelName(), cam.GetDeviceInfo().GetIpAddress())
    return fmt


def to_bgr(arr: np.ndarray, fmt: str | None) -> np.ndarray:
    """ACE2 원시 배열 → BGR(저장용).

    🚨 포맷을 추측하지 않는다 — 배열 차원으로 판정한다.
       2차원이면 Bayer(디모자이크 필요), 3차원이면 이미 컬러다.
    """
    if arr.ndim == 3:
        if fmt == "RGB8":
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return arr                      # BGR8
    return cv2.cvtColor(arr, cv2.COLOR_BayerRG2BGR)


def to_mm(depth: np.ndarray) -> np.ndarray:
    """Blaze raw uint16 → mm. 🔴 **raw는 mm가 아니다.**

    `depth_m = raw × 10 / 65535` (근거: eval_real_depth_vq_detector.py:135,
    depth_preprocess.py:54 — 학습·평가가 쓰는 변환).
    실측 검산: raw 3022 → 461mm ✅

    ⚠️ 이 단위 버그를 닷새에 다섯 번 밟았다. 화면 DIST가 3000 근처면
       --raw-is-mm으로 우회한다.
    """
    return depth.astype(np.float32) * 10.0 / 65535.0 * 1000.0


def center_crop_view(depth):
    """평가와 동일한 center_crop 영역 (판정을 평가와 일치시킨다)."""
    h, w = depth.shape
    y0, y1 = int(h * CENTER_CROP[0]), int(h * CENTER_CROP[1])
    x0, x1 = int(w * CENTER_CROP[0]), int(w * CENTER_CROP[1])
    return depth[y0:y1, x0:x1], (x0, y0, x1, y1)


def keep_range_stats(depth):
    """⭐ 평가가 실제로 쓰는 조건으로 판정.

    반환: (crop 내 400~600mm 픽셀수, crop 내 비율%, 전체 유효율%, 중앙값mm)
    """
    crop_raw, _ = center_crop_view(depth)
    all_pct = 100.0 * (depth > 0).sum() / depth.size
    valid_mask = crop_raw > 0
    if not valid_mask.any():
        return 0, 0.0, all_pct, 0
    crop_mm = to_mm(crop_raw)
    in_band = valid_mask & (crop_mm >= KEEP_RANGE_MM[0]) & (crop_mm <= KEEP_RANGE_MM[1])
    n = int(in_band.sum())
    pct = 100.0 * n / crop_raw.size
    med = int(np.median(crop_mm[valid_mask]))
    return n, pct, all_pct, med


def colorize(depth):
    """400~600mm 대역 강조. 밖은 회색으로 죽여 '부품이 대역에 있나'를 즉시 보이게."""
    vis = np.zeros((*depth.shape, 3), np.uint8)
    lo, hi = KEEP_RANGE_MM
    depth_mm = to_mm(depth)
    valid = depth > 0
    band = valid & (depth_mm >= lo) & (depth_mm <= hi)
    out = valid & ~band
    if out.any():
        g = np.clip(depth_mm / 3000.0, 0, 1)
        gray = (60 + 60 * g).astype(np.uint8)
        vis[out] = np.stack([gray[out]] * 3, axis=-1)
    if band.any():
        norm = np.clip((depth_mm - lo) / (hi - lo), 0, 1)
        c = cv2.applyColorMap((255 * (1 - norm)).astype(np.uint8), cv2.COLORMAP_TURBO)
        vis[band] = c[band]
    return vis


def rgb_quality(bgr: np.ndarray) -> tuple[float, float, bool]:
    """🆕 RGB 품질 판정 — depth만 보면 RGB가 조용히 망가진 걸 놓친다.

    ⭐ 8/14 교훈("개수만 보면 안 된다")의 RGB판. 화면에 컬러가 떠도
       ①너무 어둡거나 ②초점이 나가면 학습에 못 쓴다. 그 둘을 숫자로 본다.

    반환: (평균 밝기 0~255, 선명도(라플라시안 분산), 합격여부)
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bright = float(gray.mean())
    # 라플라시안 분산 = 초점 지표. 전체는 비싸니 중앙 crop만.
    h, w = gray.shape
    c = gray[h // 3: 2 * h // 3, w // 3: 2 * w // 3]
    sharp = float(cv2.Laplacian(c, cv2.CV_64F).var())
    # 🚨 임계값은 현장 첫 장으로 보정할 것 — 아래는 실내 형광등 기준 초안
    ok = (30.0 <= bright <= 235.0) and (sharp >= 15.0)   # 8/24 현장 보정(초안 50은 과했다)
    return bright, sharp, ok


def next_index(out: str) -> int:
    nums = [int(m.group(1)) for f in glob.glob(os.path.join(out, "shot_*.npy"))
            if (m := re.search(r"shot_(\d+)", os.path.basename(f)))]
    return (max(nums) + 1) if nums else 1


def load_meta(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"purpose": "RGB-D dual capture for depth+color fusion (D-0)",
            "conditions": {}, "shots": {}}


def save_meta(path: str, meta: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    # ⚠️ 내부 IP를 코드에 박지 않는다(리포는 협력사 미러로도 공유됨).
    ap.add_argument("--blaze-ip", default=os.environ.get("BASLER_BLAZE_IP"))
    # 🚨 ACE2 기본 대역 = setup_camera_net.py의 SUBNETS와 일치시킨다.
    #    (7/28 캘리브 스크립트는 .20.20으로 되어 있으나 그건 두 카메라를 한 대역에
    #     두던 시절 값이고, 7/29에 대역을 분리했다. 안 열리면 --ace2-ip로 지정)
    ap.add_argument("--ace2-ip", default=os.environ.get("BASLER_ACE2_IP"))
    ap.add_argument("--out", default=os.path.expanduser("~/Desktop/dual_capture_0824"))
    ap.add_argument("--session", choices=["A", "B"], required=True,
                    help="A=학습셋(오전 60장) / B=시험지(오후 재설치 후 30장). "
                         "🚨 B는 학습에 넣지 않는다")
    ap.add_argument("--target", type=int, default=60)
    ap.add_argument("--scale", type=float, default=1.5)
    ap.add_argument("--throughput", type=float, default=20.0,
                    help="카메라당 Mbps. 프레임이 깨지면 15 → 10으로 낮출 것")
    ap.add_argument("--ace2-exposure", type=float, default=None,
                    help="µs 고정 노출. 미지정이면 auto(기본)")
    ap.add_argument("--raw-is-mm", action="store_true",
                    help="화면 DIST가 3000 근처로 뜨면(실제 50cm인데) 켤 것")
    ap.add_argument("--allow-no-rgb", action="store_true",
                    help="🚨 ACE2가 안 열려도 depth만으로 진행. 기본은 중단 "
                         "— 이 촬영의 목적이 RGB라 조용히 depth만 쌓이면 하루가 날아간다")
    args = ap.parse_args()

    if args.raw_is_mm:
        global to_mm
        to_mm = lambda d: d.astype(np.float32)   # noqa: E731
        print("⚠️ --raw-is-mm: depth를 이미 mm로 취급한다")

    os.makedirs(args.out, exist_ok=True)
    meta_path = os.path.join(args.out, "capture_meta.json")
    meta = load_meta(meta_path)

    # ---------- 카메라 열기 ----------
    print("\n=== 카메라 개방 ===")
    blaze_ip = args.blaze_ip or _autodiscover("blaze")
    if not blaze_ip:
        sys.exit("❌ Blaze를 찾지 못했습니다.\n"
                 "   1) 전원·랜케이블 확인\n"
                 "   2) sudo python bin_picking/tests/setup_camera_net.py --apply\n"
                 "   3) --blaze-ip <주소>로 직접 지정")
    blaze = open_cam(blaze_ip, args.throughput)
    setup_blaze(blaze)

    # ⭐ ACE2는 모델명 'a2A'로 찾는다 (a2A2448-23gcBAS)
    ace2, ace2_fmt = None, None
    ace2_ip = args.ace2_ip or _autodiscover("a2A")
    if ace2_ip:
        try:
            ace2 = open_cam(ace2_ip, args.throughput)
            ace2_fmt = setup_ace2(ace2, args.ace2_exposure)
        except Exception as e:
            print(f"🔴 ACE2 개방 실패: {type(e).__name__}: {e}")
            ace2 = None
    else:
        print("🔴 ACE2를 찾지 못했습니다.")

    if ace2 is None:
        msg = ("\n🚨🚨 ACE2(컬러)가 없습니다. **이 촬영의 목적이 RGB 데이터 확보**입니다.\n"
               "   depth만 찍으면 8/18 90장과 같은 것이 하나 더 생길 뿐이고,\n"
               "   재택에서 할 일(D-1~3)이 그대로 막힙니다.\n\n"
               "   확인 순서:\n"
               "   1) sudo python bin_picking/tests/setup_camera_net.py --apply\n"
               "   2) ACE2 랜포트 대역 == 카메라 IP 대역인가\n"
               "      (열거는 브로드캐스트라 '보이는데 안 열림'이 정상 증상)\n"
               "   3) --ace2-ip <주소>로 직접 지정\n"
               "   그래도 안 되면 --allow-no-rgb 로 depth만 진행할 수 있습니다.")
        if not args.allow_no_rgb:
            blaze.Close()
            sys.exit(msg)
        print(msg + "\n\n   ⚠️ --allow-no-rgb: depth만 촬영합니다.")

    # ---------- 조건 메모 ----------
    idx = next_index(args.out)
    cond = 1
    while str(cond) in meta["conditions"]:
        cond += 1
    if cond > 1:
        cond -= 1
    if str(cond) not in meta["conditions"]:
        print(f"\n=== 조건 c{cond} 메모 입력 ===")
        print("예: '형광등만, 45cm, 골판지 상자, B그룹 7종'")
        note = input("c%d 조건 > " % cond).strip() or f"condition {cond}"
        meta["conditions"][str(cond)] = note
        save_meta(meta_path, meta)

    blaze.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    if ace2 is not None:
        ace2.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    print(f"\n=== 세션 {args.session} 촬영 시작 ===")
    print(f"  {args.out} / {idx}번부터 / 목표 {args.target}장")
    if args.session == "A":
        print("  🎓 세션 A = 학습셋")
    else:
        print("  🧪 세션 B = 시험지 — 🚨 이건 학습에 넣지 않는다")
    print("🔴 부품을 400~600mm 안, 화면 중앙 2/3(흰 사각형) 안에 둘 것")
    print("[s]저장 [스페이스]조건변경 [u]취소 [q]종료\n")

    win = "Blaze(depth) + ACE2(RGB)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    last_saved = None
    last = time.time(); fps = 0.0
    n_rgb_fail = 0

    try:
        while True:
            # ---------- Blaze ----------
            res = blaze.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            if not res.GrabSucceeded():
                res.Release(); continue
            try:
                depth = res.Array.copy()
            except Exception as e:
                # 7/28 교훈: Blaze가 다른 컴포넌트를 섞어 보내면 res.Array가 ValueError
                print(f"  · depth 프레임 스킵 ({type(e).__name__})")
                res.Release(); continue
            res.Release()

            # ---------- ACE2 ----------
            bgr = None
            if ace2 is not None:
                try:
                    ra = ace2.RetrieveResult(2000, pylon.TimeoutHandling_Return)
                    if ra is not None and ra.GrabSucceeded():
                        try:
                            bgr = to_bgr(ra.Array.copy(), ace2_fmt)
                        except Exception:
                            bgr = None
                        ra.Release()
                    elif ra is not None:
                        ra.Release()
                except Exception:
                    bgr = None

            now = time.time(); fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-3)); last = now
            n_band, pct_band, all_pct, med = keep_range_stats(depth)
            depth_ok = (n_band > BAND_PX_MIN) and (KEEP_RANGE_MM[0] <= med <= KEEP_RANGE_MM[1] * 1.5)

            if bgr is not None:
                bright, sharp, rgb_ok = rgb_quality(bgr)
            else:
                bright, sharp, rgb_ok = 0.0, 0.0, False

            # 🚨 둘 다 좋아야 저장 가치가 있다 (ACE2 없이 진행 중이면 depth만 본다)
            ok = depth_ok and (rgb_ok if ace2 is not None else True)

            # ---------- 화면 ----------
            vis = colorize(depth)
            crop, (x0, y0, x1, y1) = center_crop_view(depth)
            cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 255, 255), 1)
            if args.scale != 1.0:
                vis = cv2.resize(vis, None, fx=args.scale, fy=args.scale,
                                 interpolation=cv2.INTER_NEAREST)

            # ⭐ RGB를 같은 창 우측에 붙여 **두 카메라가 같은 장면을 보는지** 눈으로 확인
            #    (7/29에 화각차로 depth 86%가 ACE2 밖이었던 전례가 있다)
            if bgr is not None:
                th = vis.shape[0]
                tw = int(bgr.shape[1] * th / bgr.shape[0])
                side = cv2.resize(bgr, (tw, th), interpolation=cv2.INTER_AREA)
                vis = np.hstack([vis, side])

            saved = idx - 1
            def put(txt, y, color, sz=0.7, th_=2):
                cv2.putText(vis, txt, (10, y), cv2.FONT_HERSHEY_SIMPLEX, sz, color, th_)

            put(f"[{args.session}] saved={saved}/{args.target}  next=shot_{idx:03d}  COND=c{cond}",
                30, (0, 255, 0), 0.8)
            put(f"BAND={n_band//1000}k ({pct_band:.0f}%)  DIST={med}mm"
                + ("" if depth_ok else "  <<< depth NG"),
                58, (0, 255, 0) if depth_ok else (0, 150, 255))
            if ace2 is not None:
                put(f"RGB bright={bright:.0f} sharp={sharp:.0f}"
                    + ("" if rgb_ok else "  <<< RGB NG (어둡거나 초점)"),
                    86, (0, 255, 0) if rgb_ok else (0, 150, 255))
            else:
                put("RGB = NONE (--allow-no-rgb)", 86, (0, 0, 255))
            put(f"(all_valid={all_pct:.0f}%  fps={fps:.1f})  {'SAVE OK' if ok else 'not ready'}",
                112, (200, 200, 200) if not ok else (0, 255, 0), 0.55, 1)
            cv2.imshow(win, vis)

            # ---------- 키 ----------
            k = cv2.waitKey(1) & 0xFF
            if k in (ord('q'), 27):
                break

            elif k == ord('s'):
                # 🚨 RGB가 필요한 촬영인데 RGB가 없으면 저장을 막는다.
                #    (조용히 depth만 쌓이는 것이 이 작업 최대의 실패 모드)
                if ace2 is not None and bgr is None:
                    n_rgb_fail += 1
                    print(f"  🔴 저장 거부: RGB 프레임이 없다 (누적 {n_rgb_fail}회). "
                          f"대역폭이면 --throughput {max(10, int(args.throughput)-5)} 로 재시작")
                    continue

                stem = f"shot_{idx:03d}_c{cond}_s{args.session}"
                base = os.path.join(args.out, stem)
                np.save(base + ".npy", depth)                     # raw uint16 (학습셋과 동일)
                cv2.imwrite(base + ".png", vis)                   # 판정용 미리보기
                rgb_name = None
                if bgr is not None:
                    rgb_name = stem + "_rgb.png"
                    # 🚨 원본 해상도·무손실. 정렬(D-1)에서 원본이 필요하다.
                    cv2.imwrite(os.path.join(args.out, rgb_name), bgr)

                meta["shots"][stem] = {
                    "session": args.session,
                    "condition": cond,
                    "condition_note": meta["conditions"].get(str(cond), ""),
                    "band_px": n_band, "band_pct": round(pct_band, 2),
                    "median_mm": med, "all_valid_pct": round(all_pct, 1),
                    "depth_ok": bool(depth_ok),
                    "rgb_file": rgb_name,
                    "rgb_shape": list(bgr.shape) if bgr is not None else None,
                    "rgb_bright": round(bright, 1), "rgb_sharp": round(sharp, 1),
                    "rgb_ok": bool(rgb_ok),
                    "ok": bool(ok),
                }
                save_meta(meta_path, meta)                        # 매 장 즉시 (유실 방지)
                print(f"[{idx}/{args.target}] {stem}  band={n_band} med={med}mm "
                      f"rgb={'OK' if rgb_ok else 'NG'} [{'OK' if ok else '..'}]")
                last_saved = (base, stem, rgb_name); idx += 1

            elif k == ord(' '):
                cond += 1
                print(f"\n=== 조건 c{cond}로 변경 — 메모 입력 ===")
                note = input("c%d 조건 > " % cond).strip() or f"condition {cond}"
                meta["conditions"][str(cond)] = note
                save_meta(meta_path, meta)
                print(f"== c{cond} = {note} ==\n")

            elif k == ord('u') and last_saved:
                base, stem, rgb_name = last_saved
                for p in (base + ".npy", base + ".png"):
                    if os.path.exists(p): os.remove(p)
                if rgb_name:
                    p = os.path.join(args.out, rgb_name)
                    if os.path.exists(p): os.remove(p)
                meta["shots"].pop(stem, None); save_meta(meta_path, meta)
                idx -= 1; print(f"↩ 취소: {stem}")
                last_saved = None

    finally:
        try: blaze.StopGrabbing(); blaze.Close()
        except Exception: pass
        if ace2 is not None:
            try: ace2.StopGrabbing(); ace2.Close()
            except Exception: pass
        cv2.destroyAllWindows()
        save_meta(meta_path, meta)

        shots = meta["shots"]
        n_a = sum(1 for v in shots.values() if v.get("session") == "A")
        n_b = sum(1 for v in shots.values() if v.get("session") == "B")
        n_rgb = sum(1 for v in shots.values() if v.get("rgb_file"))
        n_ok = sum(1 for v in shots.values() if v.get("ok"))
        print(f"\n=== 종료 ===")
        print(f"  총 {len(shots)}장 (OK {n_ok}장)  → {args.out}")
        print(f"  세션 A(학습) {n_a}장 / 세션 B(시험지) {n_b}장")
        print(f"  🎨 RGB 동봉 {n_rgb}장" + ("" if n_rgb == len(shots) else f"  🚨 {len(shots)-n_rgb}장은 RGB 없음"))
        print(f"  조건: {meta['conditions']}")
        if n_b == 0 and args.session == "A":
            print("\n  ⏭️ 다음: 카메라를 한 번 떼었다 다시 달고 --session B --target 30")
        print(f"\n  전송: scp -r {args.out} <6000>:/data/jtm/")


if __name__ == "__main__":
    main()
