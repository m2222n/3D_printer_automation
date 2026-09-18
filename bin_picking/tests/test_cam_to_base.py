"""
cam_to_base 변환 계층 자체 검증 — 카메라·로봇 없이 돈다 (numpy 필요 · /data/jtm/depth_venv/bin/python)

사용: /data/jtm/depth_venv/bin/python bin_picking/tests/test_cam_to_base.py
(다른 bin_picking/tests/*.py 와 같이 pytest 파일이 아니라 자체 실행 스크립트다 — sys.exit 로 끝난다)

검증하는 것
  🟢 합성 변환(카메라가 아래를 보는 자세) → build → save → load 왕복 · 잔차 ~0 · 점 복원
  🟢 ⭐ 9/16 실물 six.json(팔에 달린 Blaze · 검출 4건) → base 포즈 = T·camera_3d 와 일치 · hover 가 z 에만 붙는다
  🟢 rz: fixed = rz_ref 그대로 / angle = 카메라 x 축이 base 축에 놓인 알려진 기하에서 손으로 계산한 yaw 와 일치 · 180° 대표값 선택
  🟢 거부 9종: 파일 없음 · 스키마 다름 · 단위 m · 반사행렬 · 잔차 초과 · 파일 부분 수정 · camera_3d 없음 · 각도 신뢰불가(angle) · 작업영역 밖(변환 어긋남 300mm)
  🟢 물리 관문: z=3136(7/29) · m 단위(0.4) · 도달 밖 → 거부
  🟢 🥇 배선: pick_socket_server._provider_vision 이 (a) 캘리브 없으면 provider 를 만들지도 못하고 (b) 캘리브가 있으면
     **보낸 값 ≠ camera_3d** 이고 == det_to_base_pose 결과다  ← 9/1 "값 일치" 함정(카메라 좌표 왕복)을 정확히 잡는 검사
  🟢 소켓 왕복: 진짜 PickSocketServer + 가짜 로봇 클라이언트 → 로봇이 읽은 값 == base 포즈(카메라 값 아님) · DONE
  🟢 validate_pose(frame): base 규칙은 z≈120 통과·z=450 카메라값도 통과(잡지 못함 = 그래서 provider 배선 검사가 필요) / camera 규칙은 z=120 거부
  🧪 그물 확인: det_to_base_pose 를 "카메라 좌표 그대로" 로 바꿔 끼우면 배선 검사가 **실패해야** 한다(= 검사가 실제로 물려 있다)
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bin_picking.src.communication import cam_to_base as c2b  # noqa: E402
from bin_picking.src.communication import pick_socket_server as pss  # noqa: E402
from bin_picking.src.acquisition.work_coord_3point import apply_transform, make_transform  # noqa: E402
from bin_picking.tests.fake_robot_socket import run_fake_robot  # noqa: E402

PASS = FAIL = 0
REAL_SIX = REPO.parent / "data" / "jtm" / "handover_0916" / "cap_0916" / "six" / "shot_001_c1_sA.six.json"
if not REAL_SIX.exists():
    REAL_SIX = Path("/data/jtm/handover_0916/cap_0916/six/shot_001_c1_sA.six.json")


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  🟢 {name}")
    else:
        FAIL += 1
        print(f"  🔴 {name}" + (f"  — {detail}" if detail else ""))


def expect_raise(name: str, fn, exc=(c2b.CamToBaseError,), needle: str = "") -> None:
    try:
        fn()
    except exc as e:
        ok = (needle in str(e)) if needle else True
        check(name, ok, f"예외는 났으나 문구가 다름: {e}")
    except Exception as e:  # noqa: BLE001
        check(name, False, f"다른 예외 {type(e).__name__}: {e}")
    else:
        check(name, False, "예외가 나지 않았다")


# ------------------------------------------------------------
# 합성 기하 = 카메라가 P_capture 에서 **아래를 본다**
#   카메라 z(광축) → base −z · 카메라 x(화면 오른쪽) → base +y · 카메라 y(화면 아래) → base +x  (오른손 · det=+1)
#   카메라 원점 = base (-440, 220, 560) 부근 (9/16 P_capture TCP Z 413 + 툴 150 ≈ 플랜지 563)
# ------------------------------------------------------------
R_TRUE = np.array([[0.0, 1.0, 0.0],
                   [1.0, 0.0, 0.0],
                   [0.0, 0.0, -1.0]])
assert abs(np.linalg.det(R_TRUE) - 1.0) < 1e-12
T_CAM_ORIGIN = np.array([-440.0, 220.0, 560.0])
T_TRUE = make_transform(R_TRUE, T_CAM_ORIGIN)
CAPTURE_TCP = [-440.12, 222.68, 413.41, -178.85, -2.6, -90.03]   # 9/16 실측 P_capture (임시)

# 캘리브 블록 4개(카메라 좌표 · 윗면 높이 20~30) — 빈 네 모서리 근처.
# 🚨 바닥 깊이는 9/16 실물 검출과 맞춘다: 뷰어는 중앙 450 이었으나 검출 Zc 는 482~511(골판지 처짐·기울기·바닥 픽셀 섬임)
#    ⇒ 블록은 부품과 **같은 바닥**에 놓인다는 전제(9/22 절차의 핵심)라 윗면을 460~470 으로 둔다. 다르게 두면 작업영역 하한이 실물을 거부한다(첫 실행에서 실제로 그랬다).
CAM_PTS = np.array([[-200.0, -120.0, 470.0], [200.0, -120.0, 465.0],
                    [200.0, 120.0, 460.0], [-200.0, 120.0, 468.0]])
ROB_PTS = apply_transform(T_TRUE, CAM_PTS)


def build_ok_calib(path: Path, **grasp_kw) -> c2b.Calibration:
    g = c2b.GraspFrame(rz_ref_deg=-90.03, **grasp_kw)
    calib = c2b.build_calibration(CAM_PTS, ROB_PTS, CAPTURE_TCP, g, source={"test": "synthetic"}, notes="test")
    c2b.save_calibration(calib, path)
    return c2b.load_calibration(path)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="c2b_"))

    print("① build → save → load 왕복")
    calib = build_ok_calib(tmp / "ok.json")
    check("잔차 RMS ≈ 0", calib.quality["residual_rms_mm"] < 1e-6, str(calib.quality["residual_rms_mm"]))
    check("T 복원 == 원본", np.allclose(calib.T_cam_to_base, T_TRUE, atol=1e-6))
    check("P_capture 보존", np.allclose(calib.capture_pose_tcp, CAPTURE_TCP))
    check("schema/units 기록", json.loads((tmp / "ok.json").read_text())["schema"] == c2b.SCHEMA)
    for i, (c, r) in enumerate(zip(CAM_PTS, ROB_PTS), 1):
        p = c2b.camera_xyz_to_base(calib, c)
        check(f"캘리브 점 P{i} 복원 <0.01mm", np.linalg.norm(p - r) < 1e-2, f"{np.linalg.norm(p - r):.3f}")
    ws = calib.workspace
    check("작업영역 = 로봇 점 상자 ± 여유", ws.z_min < ROB_PTS[:, 2].min() and ws.z_max > ROB_PTS[:, 2].max()
          and ws.xy_min[0] < ROB_PTS[:, 0].min() - 100)

    print("\n② ⭐ 9/16 실물 six.json → base 포즈")
    if REAL_SIX.exists():
        _, dets = c2b.load_six_detections(REAL_SIX)
        check("검출 4건 로드", len(dets) == 4, str(len(dets)))
        for det in dets:
            cam = det["camera_3d"]
            xyz = np.array([cam["Xc"], cam["Yc"], cam["Zc"]])
            exp = apply_transform(T_TRUE, xyz)
            pose = c2b.det_to_base_pose(det, calib, hover_mm=0.0, rz_mode="fixed")
            check(f"{det['label']:<26} xyz == T·cam", np.allclose(pose[:3], exp, atol=1e-9), f"{pose[:3]} vs {exp}")
            check(f"{det['label']:<26} xyz ≠ camera_3d (좌표계가 실제로 바뀜)", not np.allclose(pose[:3], xyz, atol=1.0))
            check(f"{det['label']:<26} rx/ry/rz = 180/0/rz_ref", pose[3:] == [180.0, 0.0, -90.03], str(pose[3:]))
            hov = c2b.det_to_base_pose(det, calib, hover_mm=50.0)
            check(f"{det['label']:<26} hover 50 → z+50 · xy 불변", abs(hov[2] - pose[2] - 50) < 1e-9 and hov[:2] == pose[:2])
            # 9/16 장면: 바닥 ≈450 카메라 z → base z ≈ 560-450 = 110. 실물 Zc 는 482~518 까지 있다(골판지 처짐·기울기·헐거운 마스크)
            check(f"{det['label']:<26} base z 가 바닥 근처(30~200) · Zc={cam['Zc']}", 30 <= pose[2] <= 200, f"{pose[2]:.1f}")
    else:
        check("9/16 실물 six.json 존재", False, str(REAL_SIX))

    print("\n③ rz — fixed / angle")
    det0 = {"camera_3d": {"Xc": 10.0, "Yc": -20.0, "Zc": 440.0}, "angle": 0.0, "angle_reliable": True}
    check("fixed: rz == rz_ref", c2b.det_to_base_pose(det0, calib, rz_mode="fixed")[5] == -90.03)
    # 기하 손계산: 카메라 x 축(angle 0) → base +y ⇒ yaw_long = 90 ⇒ 닫힘 방향 = 180 ≡ 0 (mod 180)
    check("angle 0 → yaw_long 90 (카메라 x = base +y)", abs(c2b.part_yaw_base_deg(calib, 0.0) - 90.0) < 1e-9,
          str(c2b.part_yaw_base_deg(calib, 0.0)))
    # angle 90 (카메라 y 축) → base +x ⇒ yaw_long = 0
    check("angle 90 → yaw_long 0 (카메라 y = base +x)", abs(c2b.part_yaw_base_deg(calib, 90.0)) < 1e-9)
    # rz(angle 0) = sign*(90+90) + 0 = 180 → 180 주기에서 rz_ref(-90.03) 에 가장 가까운 대표값 = 0 또는 -180 → | -180-(-90.03)|=89.97 vs |0-(-90.03)|=90.03 ⇒ -180
    rz0 = c2b.det_to_base_pose(det0, calib, rz_mode="angle")[5]
    check("angle 0 → rz 는 180 주기 대표값(-180)", abs(rz0 - (-180.0)) < 1e-9, str(rz0))
    det45 = dict(det0, angle=45.0)
    rz45 = c2b.det_to_base_pose(det45, calib, rz_mode="angle")[5]
    check("angle 45 → rz 가 rz_ref 근처 90 주기 안(|rz-rz_ref| ≤ 90)", abs(rz45 - (-90.03)) <= 90.0 + 1e-9, str(rz45))
    calib_neg = build_ok_calib(tmp / "neg.json", rz_sign=-1)
    rz_neg = c2b.det_to_base_pose(det45, calib_neg, rz_mode="angle")[5]
    check("rz_sign=-1 이면 부호가 뒤집힌 다른 값", abs(((rz_neg - rz45) + 90) % 180 - 90) > 1.0, f"{rz45} vs {rz_neg}")
    calib_off = build_ok_calib(tmp / "off.json", rz_offset_deg=90.0)
    rz_off = c2b.det_to_base_pose(det45, calib_off, rz_mode="angle")[5]
    check("rz_offset=90 이면 90 어긋난 값", abs(abs(((rz_off - rz45) + 180) % 360 - 180) - 90.0) < 1e-6, f"{rz45} vs {rz_off}")

    print("\n④ 거부 — 캘리브 파일")
    expect_raise("파일 없음", lambda: c2b.load_calibration(tmp / "none.json"), needle="캘리브 파일이 없다")
    d = json.loads((tmp / "ok.json").read_text()); d["schema"] = "other"
    (tmp / "schema.json").write_text(json.dumps(d))
    expect_raise("스키마 다름", lambda: c2b.load_calibration(tmp / "schema.json"), needle="schema")
    d = json.loads((tmp / "ok.json").read_text()); d["units"] = "m"
    (tmp / "units.json").write_text(json.dumps(d))
    expect_raise("단위 m", lambda: c2b.load_calibration(tmp / "units.json"), needle="units")
    d = json.loads((tmp / "ok.json").read_text())
    T = np.array(d["T_cam_to_base"]); T[:3, 0] *= -1; d["T_cam_to_base"] = T.tolist()
    (tmp / "reflect.json").write_text(json.dumps(d))
    expect_raise("반사행렬(det<0)", lambda: c2b.load_calibration(tmp / "reflect.json"), needle="반사")
    d = json.loads((tmp / "ok.json").read_text()); d["quality"]["residual_rms_mm"] = 8.0
    (tmp / "rms.json").write_text(json.dumps(d))
    expect_raise("잔차 8mm", lambda: c2b.load_calibration(tmp / "rms.json"), needle="잔차")
    d = json.loads((tmp / "ok.json").read_text()); d["T_cam_to_base"][0][3] += 30.0   # 이동만 30mm 손으로 고침
    (tmp / "edited.json").write_text(json.dumps(d))
    expect_raise("파일 부분 수정(T 이동 +30 · 잔차 불일치)", lambda: c2b.load_calibration(tmp / "edited.json"), needle="재계산")
    bad_rob = ROB_PTS.copy(); bad_rob[1] += [25.0, 0, 0]
    expect_raise("build: 점 하나 25mm 어긋 → 파일 안 만든다",
                 lambda: c2b.build_calibration(CAM_PTS, bad_rob, CAPTURE_TCP), exc=Exception, needle="잔차")
    expect_raise("build: P_capture 가 m 단위(0.4,0.2,0.4)",
                 lambda: c2b.build_calibration(CAM_PTS, ROB_PTS, [0.44, 0.22, 0.41, 180, 0, -90]), needle="원점")

    print("\n⑤ 거부 — 검출·변환 결과")
    expect_raise("camera_3d 없음", lambda: c2b.det_to_base_pose({"angle": 0}, calib), needle="camera_3d")
    expect_raise("Zc=3136 (7/29 단위 사고)", lambda: c2b.det_to_base_pose({"camera_3d": {"Xc": 0, "Yc": 0, "Zc": 3136.0}}, calib), needle="200~1500")
    expect_raise("Zc=0.45 (m 단위)", lambda: c2b.det_to_base_pose({"camera_3d": {"Xc": 0.01, "Yc": 0.0, "Zc": 0.45}}, calib), needle="200~1500")
    expect_raise("angle 신뢰불가(angle 모드)",
                 lambda: c2b.det_to_base_pose({"camera_3d": {"Xc": 0, "Yc": 0, "Zc": 440}, "angle": 3.0, "angle_reliable": False, "angle_note": "aspect"}, calib, rz_mode="angle"),
                 needle="angle_reliable")
    check("angle 신뢰불가라도 fixed 모드는 통과(각도를 안 쓴다)",
          c2b.det_to_base_pose({"camera_3d": {"Xc": 0, "Yc": 0, "Zc": 440}, "angle": 3.0, "angle_reliable": False}, calib, rz_mode="fixed")[5] == -90.03)
    expect_raise("작업영역 밖: 카메라 x=+600(빈 밖 · 여유 150 초과)",
                 lambda: c2b.det_to_base_pose({"camera_3d": {"Xc": 600.0, "Yc": 0, "Zc": 440}}, calib), needle="작업영역")
    # 변환이 300mm 어긋난 캘리브(다른 P_capture 에서 찍은 상황을 흉내) → 정상 검출도 작업영역 밖
    T_shift = T_TRUE.copy(); T_shift[:3, 3] += [300.0, 0, 0]
    calib_shift = c2b.Calibration(T_cam_to_base=T_shift, quality=calib.quality, capture_pose_tcp=calib.capture_pose_tcp,
                                  workspace=calib.workspace, grasp=calib.grasp, points_camera=CAM_PTS, points_robot=ROB_PTS)
    expect_raise("변환 300mm 어긋남(P_capture 불일치 흉내) → 작업영역이 잡는다",
                 lambda: c2b.det_to_base_pose(det0, calib_shift), needle="작업영역")
    expect_raise("rz_mode 오타", lambda: c2b.det_to_base_pose(det0, calib, rz_mode="fix"), needle="rz_mode")
    expect_raise("calib=None", lambda: c2b.det_to_base_pose(det0, None), needle="None")
    ok, msg = c2b.check_capture_pose(calib, CAPTURE_TCP)
    check("P_capture 대조: 같은 자세 → 통과", ok, msg)
    ok2, msg2 = c2b.check_capture_pose(calib, [c + d for c, d in zip(CAPTURE_TCP, [0, 0, 12.0, 0, 0, 0])])
    check("P_capture 대조: z 12mm 다름 → 불통", not ok2, msg2)

    print("\n⑥ 물리 관문 (base) — check_base_point_physical / validate_pose(frame)")
    expect_raise("base |p|>1800 (z=3136)", lambda: c2b.check_base_point_physical([0, 0, 3136.0]), needle="도달")
    expect_raise("base |p|<100 (m 단위)", lambda: c2b.check_base_point_physical([0.4, 0.2, 0.1]), needle="m 단위")
    expect_raise("validate_pose base z=3136", lambda: pss.validate_pose([0, 0, 3136, 180, 0, 0], frame="base"), exc=pss.PickEncodeError, needle="도달")
    expect_raise("validate_pose base m 단위", lambda: pss.validate_pose([0.44, 0.22, 0.11, 180, 0, -90], frame="base"), exc=pss.PickEncodeError, needle="원점")
    check("validate_pose base z=120 통과(부품 높이)", pss.validate_pose([-440, 220, 120, 180, 0, -90], frame="base")[2] == 120.0)
    expect_raise("validate_pose camera z=120 거부(카메라 규칙)", lambda: pss.validate_pose([10, 20, 120, 180, 0, 0], frame="camera"), exc=pss.PickEncodeError, needle="물리 범위")
    check("validate_pose camera z=450 통과", pss.validate_pose([10, 20, 450, 180, 0, 0], frame="camera")[2] == 450.0)
    check("🚨 base 규칙은 카메라 값(z=450)을 못 잡는다 — 그래서 아래 ⑦ 배선 검사가 필요하다",
          pss.validate_pose([94.8, 250.1, 518.1, 180, 0, 0], frame="base")[2] == 518.1)
    check("six_elements_to_pose 는 카메라 규칙(z=450 통과·값 그대로)",
          pss.six_elements_to_pose({"camera_3d": {"Xc": 1, "Yc": 2, "Zc": 450}, "angle": 5.0})[:3] == [1.0, 2.0, 450.0])

    print("\n⑦ 🥇 배선 — _provider_vision 이 변환 계층을 실제로 지나는가")
    if REAL_SIX.exists():
        expect_raise("캘리브 없이 provider 생성 → 즉시 예외(로봇 접속 전)",
                     lambda: pss._provider_vision(str(REAL_SIX), 1, calib_path=None), exc=pss.PickEncodeError, needle="--calib")
        expect_raise("캘리브 파일 경로 틀림 → 즉시 예외",
                     lambda: pss._provider_vision(str(REAL_SIX), 1, calib_path=str(tmp / "none.json")), exc=pss.PickEncodeError, needle="캘리브 파일")
        expect_raise("잔차 8mm 파일 → 즉시 예외",
                     lambda: pss._provider_vision(str(REAL_SIX), 1, calib_path=str(tmp / "rms.json")), exc=pss.PickEncodeError, needle="잔차")
        prov = pss._provider_vision(str(REAL_SIX), 4, calib_path=str(tmp / "ok.json"), hover_mm=50.0)
        poses = prov()
        _, dets = c2b.load_six_detections(REAL_SIX)
        gated, _ = pss.input_gate.filter_detections(dets)
        check("보낸 개수 == 게이트 통과 검출 수", len(poses) == len(gated), f"{len(poses)} vs {len(gated)}")
        all_ne_cam = all(not np.allclose(p[:3], [d["camera_3d"]["Xc"], d["camera_3d"]["Yc"], d["camera_3d"]["Zc"]], atol=1.0)
                         for p, d in zip(poses, gated))
        check("🥇 보낸 값 ≠ camera_3d (9/1 '값 일치' 함정 = 카메라 좌표 왕복이 아니다)", all_ne_cam)
        all_eq_base = all(np.allclose(p, c2b.det_to_base_pose(d, calib, hover_mm=50.0), atol=1e-9) for p, d in zip(poses, gated))
        check("🥇 보낸 값 == det_to_base_pose(hover 50)", all_eq_base)
        check("보낸 값 z 전부 바닥+50 근처(80~250)", all(80 <= p[2] <= 250 for p in poses), str([round(p[2], 1) for p in poses]))

        print("\n⑧ 소켓 왕복 — 진짜 서버 + 가짜 로봇")
        server = pss.PickSocketServer(host="127.0.0.1", port=0, verbose=False)
        server.open()
        port = server._sock.getsockname()[1]
        res_box = {}
        def _srv():
            res_box["r"] = server.serve_cycle(prov, accept_timeout=5)
        t = threading.Thread(target=_srv, daemon=True); t.start()
        time.sleep(0.2)
        robot = run_fake_robot("127.0.0.1", port, motion_sec=0.0, verbose=False)
        t.join(10); server.close()
        r = res_box.get("r")
        check("사이클 ok · DONE", bool(r and r.ok and r.response == "DONE"), getattr(r, "error", "no result"))
        check("로봇이 읽은 값 == 서버가 보낸 base 포즈(소수점까지)", robot["poses"] == (r.poses_sent if r else None))
        check("로봇이 읽은 값 ≠ camera_3d", all(not np.allclose(p[:3], [d["camera_3d"]["Xc"], d["camera_3d"]["Yc"], d["camera_3d"]["Zc"]], atol=1.0)
                                          for p, d in zip(robot["poses"], gated)))

        print("\n🧪 그물 확인 — 변환을 '카메라 좌표 그대로' 로 바꿔 끼우면 ⑦ 검사가 실패해야 한다")
        real_fn = c2b.det_to_base_pose
        def fake_passthrough(det, calib, *, hover_mm=0.0, rz_mode="fixed", require_reliable_angle=True):
            cam = det["camera_3d"]
            return [float(cam["Xc"]), float(cam["Yc"]), float(cam["Zc"]) + hover_mm, 180.0, 0.0, -90.03]
        c2b.det_to_base_pose = fake_passthrough
        try:
            prov_bad = pss._provider_vision(str(REAL_SIX), 4, calib_path=str(tmp / "ok.json"), hover_mm=0.0)
            poses_bad = prov_bad()
            caught = not all(not np.allclose(p[:3], [d["camera_3d"]["Xc"], d["camera_3d"]["Yc"], d["camera_3d"]["Zc"]], atol=1.0)
                             for p, d in zip(poses_bad, gated))
            check("훼손 시 '보낸 값 ≠ camera_3d' 검사가 실패한다(= 검사가 살아 있다)", caught)
            check("🚨 훼손분은 validate_pose(base) 를 통과한다 — 물리 관문만으론 못 막는다는 증거", len(poses_bad) == len(gated))
        finally:
            c2b.det_to_base_pose = real_fn
        prov_ok = pss._provider_vision(str(REAL_SIX), 4, calib_path=str(tmp / "ok.json"), hover_mm=0.0)
        check("복원 후 다시 base 값", all(not np.allclose(p[:3], [d["camera_3d"]["Xc"], d["camera_3d"]["Yc"], d["camera_3d"]["Zc"]], atol=1.0)
                                        for p, d in zip(prov_ok(), gated)))
    else:
        check("⑦⑧ 실물 six.json 없음 — 배선·소켓 검사 생략", False, str(REAL_SIX))

    print("\n⑨ CLI 음수 점 값 — argparse 가 '-x,y,z' 를 옵션으로 오해하던 함정(9/17 · 9/18)")
    joined = c2b._join_negative_point_values(["check", "--calib", "x.json", "--cam-point", "-12.3,45.0,482.0", "--hover-mm", "50"])
    check("'-x,y,z' 가 --cam-point=… 로 붙는다", "--cam-point=-12.3,45.0,482.0" in joined and joined[-2:] == ["--hover-mm", "50"], str(joined))
    check("음수 단일 값(-50)·양수 점은 건드리지 않는다",
          c2b._join_negative_point_values(["--hover-mm", "-50", "--cam-point", "12,3,480"]) == ["--hover-mm", "-50", "--cam-point", "12,3,480"])

    def run_cli(args):
        try:
            return c2b.main(args)
        except SystemExit as e:       # argparse 오류 = 2
            return int(e.code) if e.code is not None else 0
    rc = run_cli(["check", "--calib", str(tmp / "ok.json"), "--cam-point", "-12.3,45.0,482.0"])
    check("check --cam-point \"-12.3,45.0,482.0\" 이 argparse 에서 죽지 않는다(rc 0)", rc == 0, f"rc={rc}")
    rc2 = run_cli(["build", "--camera-points", "1,2,480;100,2,480;1,100,480;100,100,481",
                   "--robot-points", "-500,200,50;-400,200,50;-500,300,50;-400,300,51",
                   "--capture-pose", "-440.12", "222.68", "413.41", "-178.85", "-2.6", "-90.03", "--rz-ref", "-90.03",
                   "--out", str(tmp / "neg.json")])
    check("build --robot-points 공백 없는 음수 시작 문자열 + --capture-pose 음수 6개 통과", rc2 == 0 and (tmp / "neg.json").exists(), f"rc={rc2}")

    print(f"\n{'✅' if FAIL == 0 else '🔴'} 통과 {PASS} / 실패 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
