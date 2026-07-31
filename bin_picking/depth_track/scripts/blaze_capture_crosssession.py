#!/usr/bin/env python3
"""
Blaze-112 cross-session 검증용 촬영 — 맥북에서 실행.

⭐ 목적이 `blaze_capture_100.py`와 다르다 (7/30 신설 이유)
------------------------------------------------------------
기존 100장 촬영(6/26 `real_capture100`, 7/6 `blaze_capture100_v2`)은
**학습 데이터 수집**이었고, 그룹(g1/g2/g3)의 축이 **부품 구성**이었다
(27종을 골고루 넣기 위함). 조명·거리·배경은 한 세션이라 고정.

그런데 그 2세션이 **둘 다 학습에 들어갔다**(E200 = 6/26 + 7/6 통합).
그래서 7/29 CPU 평가 F1 0.8184는 train이 섞인 값 = **재현 확인이지
일반화 측정이 아니다**. "cross-session에서 유지되나"는 리포 데이터로
원리상 검증 불가.

→ 이 스크립트는 **학습 때와 다른 조건**을 일부러 만들어 찍는다.
   그룹 축을 **부품 구성 → 촬영 조건**으로 바꾼 것이 핵심 차이.
   부품 구성만 바꾸는 것은 도메인 갭이 아니다.

⚠️ 전례: 세척기 분류가 같은 세션 0.982 → cross-session 0.34~0.70 폭락
   (7/17 "cross-session만 진실"). depth_track엔 이 검증을 한 번도 안 했다.

무엇을 바꾸고 무엇을 고정하나 (⭐ 원인 분리의 핵심)
------------------------------------------------------------
바꿈 = **물리 환경만** (조명 / 카메라 높이·각도 / 배경·빈)
고정 = **센서 설정 전부** (ShortRange, 필터 On, 848x480 uint16 raw)

  이유: 센서 설정을 바꾸면 성능이 떨어졌을 때 "일반화 실패"인지
        "설정 불일치"인지 구분이 안 된다. 7/6에 실제로
        LongRange로 찍혀 g2·g3 품질이 떨어진 사고가 있었다.

작업거리 = 400~600mm 필수 (🔴 타협 불가)
------------------------------------------------------------
평가 파이프라인이 `--depth_keep_range 0.40,0.60`으로 **부품 대역만
남긴다**(`reproduce_f1_0684.sh:54`). 이 범위를 벗어나면 부품 픽셀이
전부 버려져 **검출 0건**이 된다.

  ⚠️ 7/29 재택에서 실제로 이것 때문에 실패: z 중앙 4.1~4.6m(커튼·창밖)
     → 커버리지 0.4~3.4%. 원인은 Blaze 108° 초광각이라 50cm 물체가
     화면의 극히 일부였던 것.
  → 화면 하단 DIST 게이지로 **현장에서 즉시** 확인할 것.

  또한 `--center_crop '1/6,5/6'`이므로 부품은 **화면 중앙 2/3 안**에
  들어와야 한다. 가장자리 부품은 평가에서 잘려나간다.

키
------------------------------------------------------------
  s     = 저장 (shot_NNN_cN.npy + .png)
  스페이스 = **조건 그룹 변경** (c1→c2). 조건 메모를 터미널에 입력받아
             사이드카 JSON에 기록 → 나중에 어떤 조건이 취약한지 분석 가능
  u     = 직전 저장 취소
  q/ESC = 종료

실행
------------------------------------------------------------
  # 0) 카메라 네트워크 (어댑터 꽂은 뒤 한 줄)
  sudo python bin_picking/tests/setup_camera_net.py --apply

  # 1) 촬영 (목표 30장, 조건 3종 x 10장)
  cd ~/Desktop && sudo python blaze_capture_crosssession.py --scale 2

  # 2) 6000으로 전송 후 추론 (맥엔 GPU 없음)
  scp -r ~/Desktop/blaze_crosssession_0731 <6000>:/data/jtm/
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
# ============================================================
# 근거: reproduce_f1_0684.sh:54 --depth_keep_range '0.40,0.60'
KEEP_RANGE_MM = (400, 600)
# 근거: reproduce_f1_0684.sh:53 --center_crop '1/6,5/6'
CENTER_CROP = (1 / 6, 5 / 6)


def _try(label, fn):
    try:
        fn(); print(f"  ✓ {label}"); return True
    except Exception as e:
        print(f"  · {label} 건너뜀 ({type(e).__name__})"); return False


def _autodiscover_blaze(tl):
    """--ip 미지정 시 열거로 Blaze를 찾는다.

    🐛 7/31 현장: 환경변수 없이 sudo로 돌리면 IP가 비어 스크립트가 죽었다.
    열거(브로드캐스트)는 대역이 어긋나도 되므로 여기서 실제 IP를 얻어 안내한다.
    ⚠️ 단 **열기는 유니캐스트**라 대역이 맞아야 한다 → [[gige-camera-network-rule]]
    """
    found = []
    for d in tl.EnumerateDevices():
        try:
            name, ip = d.GetModelName(), d.GetIpAddress()
        except Exception:
            continue
        if "blaze" in (name or "").lower():
            found.append((name, ip))
    if not found:
        raise SystemExit(
            "❌ Blaze를 찾지 못했습니다.\n"
            "   1) 카메라 전원·랜케이블 확인\n"
            "   2) sudo python bin_picking/tests/setup_camera_net.py --apply\n"
            "   3) 그래도 안 되면 --ip <주소> 로 직접 지정"
        )
    name, ip = found[0]
    print(f"🔎 Blaze 자동 발견: {name} @ {ip}  (고정하려면 --ip {ip})")
    if len(found) > 1:
        print(f"   ⚠️ Blaze가 {len(found)}대 보입니다. 첫 번째를 씁니다 — 의도와 다르면 --ip로 지정하세요.")
    return ip


def open_blaze(ip: str | None):
    """blaze_capture_100.py와 **동일 설정**. 센서 설정은 고정이 원칙."""
    tl = pylon.TlFactory.GetInstance(); tl.CreateTl("BaslerGigE")
    if not ip or ip.startswith("<"):
        ip = _autodiscover_blaze(tl)
    di = pylon.CDeviceInfo(); di.SetIpAddress(ip); di.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tl.CreateDevice(di)); cam.Open()
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
    print("연결:", cam.GetDeviceInfo().GetModelName(), cam.GetDeviceInfo().GetIpAddress())

    print("[depth 품질 파라미터 — 학습셋과 동일하게 고정]")
    # 🔴 ShortRange는 경고가 아니라 **종료** 사유로 격상 (7/30 변경).
    #    이유: 7/6에 LongRange로 찍혀 g2·g3 품질저하가 발생했고,
    #    현장에서 조용히 잘못 찍히면 하루가 날아간다. cross-session
    #    검증은 조건 하나만 어긋나도 결과 해석이 불가능해진다.
    ok = _try("OperatingMode=ShortRange", lambda: cam.OperatingMode.SetValue("ShortRange"))
    try:
        cur = cam.OperatingMode.GetValue()
        if cur == "ShortRange":
            print(f"  ✅ OperatingMode = {cur} (학습셋과 일치)")
        else:
            cam.Close()
            sys.exit(
                f"\n🔴🔴 중단: OperatingMode = {cur} (ShortRange 아님, set성공={ok})\n"
                "   학습셋이 ShortRange라 이대로 찍으면 cross-session 결과를\n"
                "   '일반화 실패'인지 '설정 불일치'인지 구분할 수 없습니다.\n"
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
    return cam


def to_mm(depth: np.ndarray) -> np.ndarray:
    """Blaze raw uint16 → mm. 🔴 **raw는 mm가 아니다.**

    ⚠️⚠️ 7/29에 이것 때문에 z가 6~7배 과대(3136mm)로 나왔다. 저장된 npy는 uint16이지만
    단위가 mm가 아니라 **`depth_m = raw × 10 / 65535`** 다
    (근거: `mentoring_new/eval_real_depth_vq_detector.py:135`,
     `depth_preprocess.py:54` — 학습·평가가 쓰는 변환).

    실측 검산: raw 3022 → 461mm ✅ (부품 대역 400~600 안)

    🚨 **기존 `blaze_capture_100.py`도 같은 오류가 있었다** — `part_stats`가 raw를 그대로
       쓰면서 화면에 `med=3022mm`로 표시했다(실제 461mm). 그 스크립트는 **상대 대역**
       (중앙값 ±100)만 봤기 때문에 촬영 자체는 됐지만 **표시된 숫자는 틀렸다.**
       이 스크립트는 **절대 대역 400~600mm**를 판정하므로 변환이 필수다.

    ⚠️ 라이브 카메라가 주는 값도 동일 raw 스케일인지는 **현장 확인 필요**
       (`Coord3D_C16` 픽셀 포맷 기준). 화면 DIST 값이 400~600 근처로 나오면 맞다.
       만약 현장에서 DIST가 3000 근처로 뜨면 이 함수를 우회(raw가 이미 mm)해야 한다
       → `--raw-is-mm` 플래그로 대응.
    """
    return depth.astype(np.float32) * 10.0 / 65535.0 * 1000.0


def center_crop_view(depth):
    """평가와 동일한 center_crop 영역만 잘라낸다 (판정을 평가와 일치시키기 위함)."""
    h, w = depth.shape
    y0, y1 = int(h * CENTER_CROP[0]), int(h * CENTER_CROP[1])
    x0, x1 = int(w * CENTER_CROP[0]), int(w * CENTER_CROP[1])
    return depth[y0:y1, x0:x1], (x0, y0, x1, y1)


def keep_range_stats(depth):
    """⭐ 평가가 실제로 쓰는 조건으로 판정.

    반환: (crop 내 400~600mm 픽셀수, crop 내 비율%, 전체 유효율%, 중앙값mm)

    ⚠️ 전체 화면이 아니라 **center_crop 안**에서 센다. 평가가 그렇게 하기
       때문(`--center_crop 1/6,5/6`). 가장자리에만 부품이 있으면 평가에서
       잘려 검출 0건이 되는데, 전체 화면으로 세면 그걸 못 잡아낸다.
    """
    crop_raw, _ = center_crop_view(depth)
    all_pct = 100.0 * (depth > 0).sum() / depth.size
    valid_mask = crop_raw > 0
    if not valid_mask.any():
        return 0, 0.0, all_pct, 0
    # 🔴 mm로 변환한 뒤에 대역을 본다 (raw는 mm가 아님, to_mm 주석 참조)
    crop_mm = to_mm(crop_raw)
    in_band = valid_mask & (crop_mm >= KEEP_RANGE_MM[0]) & (crop_mm <= KEEP_RANGE_MM[1])
    n = int(in_band.sum())
    pct = 100.0 * n / crop_raw.size
    med = int(np.median(crop_mm[valid_mask]))
    return n, pct, all_pct, med


def colorize(depth):
    """⭐ 400~600mm 대역을 강조. 밖은 회색으로 죽여 '부품이 대역에 있나'를 즉시 보이게."""
    vis = np.zeros((*depth.shape, 3), np.uint8)
    lo, hi = KEEP_RANGE_MM
    depth_mm = to_mm(depth)          # 🔴 raw는 mm가 아님
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


def next_index(out: str) -> int:
    nums = [int(m.group(1)) for f in glob.glob(os.path.join(out, "shot_*.npy"))
            if (m := re.search(r"shot_(\d+)", os.path.basename(f)))]
    return (max(nums) + 1) if nums else 1


def load_meta(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"purpose": "cross-session generalization check", "conditions": {}, "shots": {}}


def save_meta(path: str, meta: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    # ⚠️ 내부 IP를 코드에 박지 않는다(리포는 한솔 미러로도 공유됨).
    #    환경변수 또는 --ip로 넘길 것. `blaze_capture_100.py:121`과 같은 규약.
    # 🐛 7/31 현장 버그: 환경변수가 없으면 플레이스홀더 문자열이 그대로 넘어가
    #    `Failed to discover GigE device '<BLAZE_IP>'`로 죽었다(sudo라 셸 환경변수도 안 넘어감).
    #    → 미지정이면 None으로 두고 아래에서 자동 탐색 + 안내.
    ap.add_argument("--ip", default=os.environ.get("BASLER_BLAZE_IP"))
    ap.add_argument("--out", default=os.path.expanduser("~/Desktop/blaze_crosssession_0731"))
    ap.add_argument("--target", type=int, default=30, help="목표 장수 (조건 3종 x 10장)")
    ap.add_argument("--scale", type=float, default=2.0)
    # 🔴 현장 탈출구: 라이브 값이 이미 mm면(DIST가 400~600 대신 3000 근처로 뜨면 반대 상황)
    #    이 플래그로 변환을 끈다. 저장 원본(raw)은 어느 쪽이든 그대로 저장되므로 안전.
    ap.add_argument("--raw-is-mm", action="store_true",
                    help="라이브 depth가 이미 mm 단위일 때. 화면 DIST가 3000 근처로 "
                         "뜨면(실제 50cm 촬영인데) 이 플래그를 켤 것")
    args = ap.parse_args()
    if args.raw_is_mm:
        global to_mm
        to_mm = lambda d: d.astype(np.float32)   # noqa: E731
        print("⚠️ --raw-is-mm: depth를 이미 mm로 취급한다")
    os.makedirs(args.out, exist_ok=True)

    meta_path = os.path.join(args.out, "capture_meta.json")
    meta = load_meta(meta_path)

    cam = open_blaze(args.ip)
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    idx = next_index(args.out)
    cond = 1
    while str(cond) in meta["conditions"]:   # 이어찍기 시 조건 번호도 이어감
        cond += 1
    if cond > 1:
        cond -= 1

    if str(cond) not in meta["conditions"]:
        print(f"\n=== 조건 c{cond} 메모 입력 ===")
        print("예: '형광등만, 높이 55cm, 무광 빈' / 나중에 취약 조건 분석에 씀")
        note = input("c%d 조건 > " % cond).strip() or f"condition {cond}"
        meta["conditions"][str(cond)] = note
        save_meta(meta_path, meta)

    last_saved = None
    print(f"\ncross-session 촬영 시작 — {args.out} / {idx}번부터 / 목표 {args.target}장")
    print("🔴 부품을 400~600mm 안, 화면 중앙 2/3 안에 둘 것 (평가 조건)")
    print("[s]저장 [스페이스]조건변경 [u]취소 [q]종료\n")

    win = "Blaze cross-session"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, int(848 * args.scale), int(480 * args.scale))
    last = time.time(); fps = 0.0
    try:
        while True:
            res = cam.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            if not res.GrabSucceeded():
                res.Release(); continue
            try:
                depth = res.Array.copy()
            except Exception as e:
                # 7/28 교훈: Blaze가 간헐적으로 다른 컴포넌트를 섞어 보내면
                # res.Array가 ValueError → 프레임만 건너뛰고 죽지 않는다.
                print(f"  · 프레임 스킵 ({type(e).__name__})")
                res.Release(); continue
            res.Release()

            now = time.time(); fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-3)); last = now
            n_band, pct_band, all_pct, med = keep_range_stats(depth)

            # ⭐ 판정 = "평가가 볼 영역에 부품이 충분히 있나"
            #    n_band 기준은 학습셋 실측(부품 px 10k+)을 crop 면적으로 환산한 값
            ok = (n_band > 8000) and (KEEP_RANGE_MM[0] <= med <= KEEP_RANGE_MM[1] * 1.5)

            vis = colorize(depth)
            crop, (x0, y0, x1, y1) = center_crop_view(depth)
            cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 255, 255), 1)

            if args.scale != 1.0:
                vis = cv2.resize(vis, None, fx=args.scale, fy=args.scale,
                                 interpolation=cv2.INTER_NEAREST)
            saved = idx - 1
            cv2.putText(vis, f"saved={saved}/{args.target}  next=shot_{idx:03d}  COND=c{cond}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(vis, f"BAND(400-600mm in crop)={n_band//1000}k ({pct_band:.0f}%)  [{'OK' if ok else '..'}]",
                        (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if ok else (0, 200, 255), 2)
            # 🔴 7/29 실패(z 4.1m=커튼)를 현장에서 바로 잡기 위한 게이지
            dist_msg = f"DIST med={med}mm"
            if med and not (KEEP_RANGE_MM[0] <= med <= KEEP_RANGE_MM[1] * 1.5):
                dist_msg += "  <<< TOO FAR/NEAR! move camera"
            cv2.putText(vis, dist_msg, (10, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if (med and KEEP_RANGE_MM[0] <= med <= KEEP_RANGE_MM[1] * 1.5)
                        else (0, 100, 255), 2)
            cv2.putText(vis, f"(all_valid={all_pct:.0f}% fps={fps:.1f}) white box = eval crop region",
                        (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow(win, vis)

            k = cv2.waitKey(1) & 0xFF
            if k in (ord('q'), 27):
                break
            elif k == ord('s'):
                stem = f"shot_{idx:03d}_c{cond}"
                base = os.path.join(args.out, stem)
                np.save(base + ".npy", depth)          # raw uint16 (학습셋과 동일 포맷)
                cv2.imwrite(base + ".png", vis)
                meta["shots"][stem] = {
                    "condition": cond,
                    "condition_note": meta["conditions"].get(str(cond), ""),
                    "band_px": n_band, "band_pct": round(pct_band, 2),
                    "median_mm": med, "all_valid_pct": round(all_pct, 1),
                    "ok": bool(ok),
                }
                save_meta(meta_path, meta)             # 매 장 즉시 기록 (유실 방지)
                print(f"[{idx}/{args.target}] {stem}  band={n_band} med={med}mm [{'OK' if ok else '..'}]")
                last_saved = (base, stem); idx += 1
            elif k == ord(' '):
                cond += 1
                print(f"\n=== 조건 c{cond}로 변경 — 메모 입력 ===")
                note = input("c%d 조건 > " % cond).strip() or f"condition {cond}"
                meta["conditions"][str(cond)] = note
                save_meta(meta_path, meta)
                print(f"== c{cond} = {note} ==\n")
            elif k == ord('u') and last_saved:
                base, stem = last_saved
                for ext in (".npy", ".png"):
                    p = base + ext
                    if os.path.exists(p): os.remove(p)
                meta["shots"].pop(stem, None); save_meta(meta_path, meta)
                idx -= 1; print(f"↩ 취소: {stem}")
                last_saved = None
    finally:
        cam.StopGrabbing(); cam.Close(); cv2.destroyAllWindows()
        save_meta(meta_path, meta)
        n_ok = sum(1 for v in meta["shots"].values() if v.get("ok"))
        print(f"\n종료. 총 {idx-1}장 (OK {n_ok}장) → {args.out}")
        print(f"조건: {meta['conditions']}")
        print("\n다음: scp -r %s <6000>:/data/jtm/ 후 추론" % args.out)


if __name__ == "__main__":
    main()
