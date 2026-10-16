"""ROI 마스크 검증 — 10/12 (실행: python bin_picking/tests/test_roi_mask.py · pytest 아님)

① 모듈 자체 시험(합성 빈 · exclude · 그물)
② 🥇 배선 검사 — "짜여 있다 ≠ 호출된다"(9/1): run_live_pick / find_calib_blobs / pick_socket_server 가 실제로 부르는가
③ 부품 이름 필터(filter_by_labels)
④ 실물 프레임(있을 때만) — 10/12 447mm 에서 include 가 빈 안쪽을 잡고 유효율이 2~25% 로 들어온다
"""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bin_picking.src.pipeline import roi_mask  # noqa: E402

OK = True


def check(name: str, cond: bool) -> None:
    global OK
    print(("  🟢 " if cond else "  🔴 ") + name)
    OK = OK and bool(cond)


def main() -> int:
    print("① 모듈 자체 시험")
    check("roi_mask --self-test 통과", roi_mask._self_test() == 0)

    print("② 배선 검사 — 호출이 실제로 있는가")
    import bin_picking.src.run_live_pick as rlp
    src = inspect.getsource(rlp.main)
    i_apply, i_e2e, i_rescore = src.find("roi_mask.apply_to_file"), src.find("run_e2e("), src.find("rescore_scene_in_roi")
    check("run_live_pick.main 이 roi_mask.apply_to_file 을 부른다", i_apply > 0)
    check("… 추론(run_e2e) **앞에서** 건다", 0 < i_apply < i_e2e)
    check("… 추론 뒤 장면 게이트를 ROI 기준으로 다시 쓴다", i_rescore > i_e2e)
    check("run_live_pick 에 --roi / --only-labels 옵션", '"--roi"' in src and '"--only-labels"' in src)
    check("serve 가 --only-labels 를 소켓 서버에 넘긴다", "--only-labels" in inspect.getsource(rlp.serve))
    fcb = (REPO / "bin_picking/tests/find_calib_blobs.py").read_text(encoding="utf-8")
    check("find_calib_blobs 가 --roi 로 apply_roi 를 부른다", '"--roi"' in fcb and "roi_mask.apply_roi" in fcb)
    import bin_picking.src.communication.pick_socket_server as pss
    psrc = inspect.getsource(pss._provider_vision)
    check("pick_socket_server vision 이 filter_by_labels 를 부른다(크기 게이트 뒤·포즈 변환 앞)",
          0 < psrc.find("filter_detections") < psrc.find("filter_by_labels") < psrc.find("det_to_base_pose"))
    check("pick_socket_server main 에 --only-labels", '"--only-labels"' in inspect.getsource(pss.main))

    print("②' 🆕 10/16 셀B 웹 보고 배선 — 호출이 실제로 있는가")
    i_report = src.find("report_scene(")
    check("run_live_pick.main 이 report_scene 을 부른다", i_report > 0)
    check("… ROI 재판정 **뒤**, 소켓 서버 **앞**에서 부른다(화면 판정 = 로봇 판정 · 로봇 대기 전에 화면에 뜬다)",
          0 < i_rescore < i_report < src.find("serve("))
    check("run_live_pick 에 --report-url 옵션", '"--report-url"' in src)
    rsrc = inspect.getsource(rlp.report_scene)
    check("report_scene 이 web_reporter.http_transport 로 보낸다", "http_transport(" in rsrc and "report_bin_picking(" in rsrc)
    check("🔒 비번을 인자로 받지 않는다(환경변수만)", "password" not in src.lower().split("--report-url")[0][-200:]
          and "BINPICK_REPORT_PASSWORD" in inspect.getsource(rlp._report_token))
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); closed_port = s.getsockname()[1]; s.close()   # 확실히 닫힌 포트
    import json as _j, tempfile as _t
    with _t.TemporaryDirectory() as td:
        p = Path(td) / "x.six.json"
        p.write_text(_j.dumps({"scene_id": "x", "detections": []}), encoding="utf-8")
        try:
            ok = rlp.report_scene(p, f"http://127.0.0.1:{closed_port}", 1.0)
            check("서버가 꺼져 있어도 예외 없이 False(로봇은 계속)", ok is False)
        except Exception as e:  # noqa: BLE001
            check(f"서버가 꺼져 있어도 예외 없이 False — 예외 발생 {type(e).__name__}", False)
    # 🐛 10/16 공장: Cloudflare 터널이 Python 기본 UA 를 403 — 로그인·보고 둘 다 UA 를 실어야 한다
    from bin_picking.src.communication import web_reporter as _wr
    check("로그인·보고 요청에 User-Agent 를 싣는다(터널 403 방지)",
          "User-Agent" in inspect.getsource(rlp._report_token) and "User-Agent" in inspect.getsource(_wr.http_transport)
          and "urllib" not in _wr.HTTP_USER_AGENT)
    check("_base_url 은 전체 경로·끝 슬래시를 정리한다",
          rlp._base_url("http://h:8085/api/v1/binpick/reports/") == "http://h:8085" == rlp._base_url("http://h:8085"))

    print("③ 부품 이름 필터")
    dets = [{"label": "02_sol_block_b"}, {"label": "r_guide_a_r"}, {"label": "plate_e"}]
    keep, drop = pss.filter_by_labels(dets, ["02_sol_block_b", "plate_e", "13_x2_bcf8ccb4"])
    check("허용 2 남고 1 버림", [d["label"] for d in keep] == ["02_sol_block_b", "plate_e"] and len(drop) == 1)
    keep, drop = pss.filter_by_labels(dets, [])
    check("비우면 전부 통과(기본 동작 불변)", len(keep) == 3 and not drop)
    keep, drop = pss.filter_by_labels(dets, [" plate_e "])
    check("공백은 무시", [d["label"] for d in keep] == ["plate_e"])

    print("④ 실물 프레임(10/12 447mm · 있을 때만)")
    real = Path("/data/jtm/handover_1012/r1012/view/shot_001_c1_sA.npy")
    cfg = REPO / "bin_picking/config/roi/roi_1012_pcapture447.json"
    if real.exists():
        raw = np.load(real)
        r = roi_mask.propose_roi(raw)
        u0, v0, u1, v1 = r["include"]
        check(f"propose 가 빈 안쪽을 잡는다 {r['include']} (손 실측 ~[205,45,605,430])", 195 <= u0 <= 225 and 25 <= v0 <= 60 and 580 <= u1 <= 615 and 395 <= v1 <= 440)
        st = roi_mask.roi_stats(raw, roi_mask.load_roi(cfg))
        check(f"설정 파일로 마스크 뒤 전체 유효% {st['after']['valid_pct']} (전 {st['before']['valid_pct']})", st["after"]["valid_pct"] < 5 < st["before"]["valid_pct"])
        from bin_picking.src.pipeline import input_gate
        sub = roi_mask.apply_roi(raw, roi_mask.load_roi(cfg))[v0:v1, u0:u1]
        sc = input_gate.check_scene(sub)
        check(f"빈 안쪽 기준 장면 = {sc['verdict']}({sc['valid_ratio_pct']}%)", sc["verdict"] == "in_distribution")
        # 🧪 그물: 마스크를 안 걸면 분포 밖이어야 한다(걸어도 같으면 마스크가 의미 없다)
        sc0 = input_gate.check_scene(raw)
        check(f"🧪 그물: 마스크 없이는 분포 밖 {sc0['verdict']}({sc0['valid_ratio_pct']}%)", sc0["verdict"] != "in_distribution")
        # 🆕 10/16 재판정이 요약 판정까지 바꾸는가 — 웹 보고는 gate_summary.scene_verdict 를 읽는다
        import json, tempfile
        from bin_picking.src.communication.web_reporter import build_bin_picking_payload
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            masked = td / "m.npy"
            np.save(masked, roi_mask.apply_roi(raw, roi_mask.load_roi(cfg)))
            six_p = td / "s.six.json"
            six_p.write_text(json.dumps({"scene_id": "t", "detections": [],
                                         "gate_scene": {"verdict": "out_of_distribution", "valid_ratio_pct": 0.9},
                                         "gate_summary": {"scene_verdict": "out_of_distribution", "n_dropped": 0}}), encoding="utf-8")
            roi_mask.rescore_scene_in_roi(six_p, masked, cfg)
            d = json.loads(six_p.read_text(encoding="utf-8"))
            check("재판정이 gate_summary.scene_verdict 도 바꾼다(장면 판정과 같다)",
                  d["gate_summary"]["scene_verdict"] == d["gate_scene"]["verdict"] == "in_distribution")
            check("… 원래 전체 화면 판정은 scene_verdict_full_frame 에 남긴다",
                  d["gate_summary"].get("scene_verdict_full_frame") == "out_of_distribution")
            check("웹 payload 판정 = 빈 안쪽 판정(화면과 로봇이 같은 판정을 본다)",
                  build_bin_picking_payload(d)["scene_gate"]["verdict"] == "in_distribution")
    else:
        print("  ⚪ 실물 npy 없음 — 6000 에서만 도는 항목(건너뜀)")
    check("설정 파일 스키마 로드", roi_mask.load_roi(cfg)["include"] == [212, 32, 590, 406])

    print("  ✅ 통과" if OK else "  🔴 실패")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
