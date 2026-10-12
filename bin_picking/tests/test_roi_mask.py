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
    else:
        print("  ⚪ 실물 npy 없음 — 6000 에서만 도는 항목(건너뜀)")
    check("설정 파일 스키마 로드", roi_mask.load_roi(cfg)["include"] == [212, 32, 590, 406])

    print("  ✅ 통과" if OK else "  🔴 실패")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
