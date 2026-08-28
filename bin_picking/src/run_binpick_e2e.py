#!/usr/bin/env python3
"""빈피킹 E2E 러너 — depth 1장 → 추론 → 6요소 → 게이트 → 웹 보고까지 한 명령.

⭐⭐ 왜 이 파일이 필요한가 (2026-08-21 태민님 지적)
   조각은 각각 검증됐는데 **잇는 것이 0건**이었다:
     ① 촬영      `blaze_capture_crosssession.py`   사람이 CLI
     ② 추론      `infer_depth_vq_detector.py`      사람이 CLI
     ③ 6요소     `depth_track_to_6elements.py`     사람이 CLI
     ④ 게이트    (③에 기본 적용)
     ⑤ 웹 보고   `web_reporter.py`                 호출자가 없었다
   ⇒ 공장에서 사람이 CLI를 순서대로 쳐야 하고, **플래그 하나를 빠뜨리면 조용히 틀린다.**

🚨🚨 그 "조용히 틀리는" 것이 실제로 있었다 (8/14 실측)
   `--real_uint16_max_depth_m`를 빼면 검출이 9건→10건으로 **더 많이** 나오는데
   좌우(`_l`/`_r`)가 뒤바뀌고 부품 종류가 달라진다. **에러도 경고도 없다.**
   ⇒ ⭐ **그래서 이 러너는 검증된 플래그를 코드에 못박는다.** 사람이 매번 치지 않는다.

🚨 `main_pipeline.py`와 다르다 — 그 파일은 4월 FPFH 시절 코드로 `depth_track`을
   부르지 않는다(grep 0건). 이름 때문에 "메인"으로 오해하기 쉬우니 여기 적어둔다.

🚨🚨 **알려진 한계 = 지연 (2026-08-21 A100 실측)**
   장당 **6.7~7.5초**. 🔴 **KTR 정량목표 ②("응답 3초")를 넘는다.**
   ⭐ **원인은 추론이 느린 게 아니다** — 8/5 실측은 **추론 웜 2.45초 / 모델 로드 0.62초**였다.
     이 러너가 `subprocess`로 **매번 프로세스를 새로 띄워 모델을 다시 로드**하기 때문이다.
   ⇒ 📌 **해법 = 상주 프로세스(모델을 한 번 로드해 유지)로 바꾸는 것.**
     지금 구조를 택한 이유는 **6000에 torch가 없어도 나머지 단계를 돌릴 수 있게** 하려던 것이고,
     **"되는 것을 먼저"**(8/14 원칙)에 맞다. 🚨 **단 이 상태로 KTR을 재면 떨어진다.**
   ⚠️ KTR 대상이 빈피킹 추론인지 통합 모니터링인지는 **미확인**(대표님 확인 항목 ④).

⚠️ 범위 = **웹 전달까지**다(8/5 회의: 로봇 제어는 이번 사업 전부 제외).
   소켓 좌표 전송(`pick_socket_server.py`)은 만들어져 있고 801건 왕복 검증됐으나
   **이 러너가 자동으로 로봇을 움직이지 않는다.** `--emit-poses`로 좌표만 파일에 남긴다.

사용:
    # 1장
    python -m bin_picking.src.run_binpick_e2e --depth shot_001.npy --out-dir /tmp/e2e

    # 디렉토리 일괄 + 웹 보고
    python -m bin_picking.src.run_binpick_e2e --depth-dir captures/ --out-dir /tmp/e2e \\
        --web-url http://127.0.0.1:8085/api/v1/binpick/reports

    # 웹 없이 파일로만 (서버 없이 검증)
    python -m bin_picking.src.run_binpick_e2e --depth-dir captures/ --out-dir /tmp/e2e
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# ⭐⭐ 검증된 추론 플래그 — 여기를 사람이 매번 치지 않게 못박는다
# ---------------------------------------------------------------------------
#
# 출처 = 8/14 IPC 검증 명령(`bin_picking/docs/ipc_setup_0814.md`)에서
#        6000과 소수점까지 일치한 그 조합. + 8/20 스윕으로 교체된 임계값.
#
# 🚨 각 값이 왜 그 값인지:
#   real_uint16_max_depth_m 10.0  = raw uint16 → m 변환 계수. **빼면 조용히 틀린다**
#                                   (8/14: 좌우가 뒤바뀌는데 무경고. depth 단위 계열 6번째)
#   center_crop  1/6,5/6          = 학습과 같은 크롭. 바꾸면 게이트 임계(230px)도 무효
#   depth_keep_range 0.40,0.60    = 모델 쪽 제약(상자 규격과 무관)
#   score_thresh 0.20             = 8/20 스윕 최적점(0.45→0.20, F1 0.5445→0.5838).
#                                   🚨 recall은 0.10에서 포화하므로 더 내리면 FP만 는다
#   score_mode det                = KAIST 실측에서 최고(product 0.679 / cad 0.527)
INFER_FLAGS = [
    "--real_uint16_max_depth_m", "10.0",
    "--center_crop", "1/6,5/6",
    "--depth_keep_range", "0.40,0.60",
    "--score_thresh", "0.20",
    "--mask_thresh", "0.5",
    "--score_mode", "det",
]

DEFAULT_CKPT = REPO / "bin_picking" / "models" / "T100_best.pt"
MENTORING = REPO / "bin_picking" / "depth_track" / "mentoring_new"


class E2EError(RuntimeError):
    """어느 단계에서 멈췄는지 알리는 예외.

    🚨 원칙 = **조용히 틀리지 말고 크게 실패하라.** 단계 이름을 반드시 싣는다
       — 8/12에 "설정은 됐는데 다른 게 가로챈다"를 세 번 겪었고, 그때 시간을 잡아먹은 것이
       *"어디서 막혔는지 모르는 상태"* 였다.
    """


def _find_checkpoint(explicit: Optional[Path]) -> Path:
    """체크포인트를 찾는다. 🚨 폴백으로 아무 .pt나 집지 않는다."""
    if explicit:
        if not explicit.exists():
            raise E2EError(f"[체크포인트] 지정한 파일이 없다: {explicit}")
        return explicit
    if DEFAULT_CKPT.exists():
        return DEFAULT_CKPT
    raise E2EError(
        f"[체크포인트] 기본 경로에 없다: {DEFAULT_CKPT}\n"
        "  → --checkpoint 로 경로를 주거나 T100_best.pt를 그 자리에 두라.\n"
        "  🚨 c1plus(8/7 재학습분)를 쓰지 말 것 — holdout F1이 떨어져 배포하지 않았다."
    )


def step_infer(depth: Path, ckpt: Path, out_dir: Path, *, python: str) -> Path:
    """① 추론 — 검증된 플래그로 `infer_depth_vq_detector.py`를 부른다.

    반환 = 예측 JSON 경로.
    ⚠️ subprocess로 부르는 이유 = 이 스크립트가 torch를 import하지 않아도 되게(6000엔 torch가 없다).
       추론은 GPU/torch가 있는 곳에서만 돌고, 나머지 단계는 어디서나 돈다.
    """
    pred_dir = out_dir / "pred"
    pred_dir.mkdir(parents=True, exist_ok=True)
    cmd = [python, "infer_depth_vq_detector.py",
           "--checkpoint", str(ckpt), "--depth", str(depth),
           "--out_dir", str(pred_dir)] + INFER_FLAGS
    r = subprocess.run(cmd, cwd=str(MENTORING), capture_output=True, text=True)
    if r.returncode != 0:
        raise E2EError(
            f"[① 추론] 실패 (exit {r.returncode})\n"
            f"  명령: {' '.join(cmd)}\n"
            f"  stderr(마지막 20줄):\n" + "\n".join(r.stderr.strip().split("\n")[-20:])
        )
    # 예측 JSON 찾기 — 파일명 규약을 추측하지 않고 실제로 찾는다
    cands = sorted(pred_dir.glob(f"{depth.stem}*.json")) or sorted(pred_dir.glob("*.json"))
    if not cands:
        raise E2EError(
            f"[① 추론] 성공했다는데 예측 JSON이 없다: {pred_dir}\n"
            f"  stdout: {r.stdout.strip()[-300:]}"
        )
    return cands[-1]


def step_six(pred_json: Path, depth: Path, out_dir: Path, *, python: str) -> Path:
    """② 6요소 변환 + ③ 게이트(기본 적용).

    ⚠️ 게이트를 끄지 않는다 — `depth_track_to_6elements`가 `--no-gate` 없으면 기본 적용이다.
       8/5에 "단일 출처를 만들었는데 호출자가 안 쓴" 전례가 있어 **기본값을 신뢰**한다.
    """
    six_dir = out_dir / "six"
    six_dir.mkdir(parents=True, exist_ok=True)
    six_path = six_dir / f"{depth.stem}.six.json"
    cmd = [python, "-m", "bin_picking.src.pipeline.depth_track_to_6elements",
           "--pred", str(pred_json), "--out", str(six_path),
           "--depth-dir", str(depth.parent)]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        raise E2EError(
            f"[② 6요소] 실패 (exit {r.returncode})\n"
            f"  명령: {' '.join(cmd)}\n"
            f"  stderr:\n{r.stderr.strip()[-1200:]}"
        )
    if not six_path.exists():
        raise E2EError(f"[② 6요소] 성공했다는데 출력이 없다: {six_path}")
    return six_path


def step_report(six_path: Path, *, web_url: Optional[str], out_dir: Path,
                latency_ms: float) -> dict:
    """④ 웹 보고. 🚨 **실패해도 예외를 던지지 않는다**(설계원칙 1: 웹은 보고 경로다).

    ⭐ 단 조용히 삼키지도 않는다 — 성패와 원인을 반환값에 남긴다.
    """
    from bin_picking.src.communication import web_reporter as WR

    six = json.loads(six_path.read_text())
    if web_url:
        transport = WR.http_transport(web_url)
        where = web_url
    else:
        sent_dir = out_dir / "web_payload"
        transport = WR.file_transport(sent_dir)
        where = str(sent_dir)
    # 🚨 클래스명은 추측하지 말고 파일에서 확인한 것을 쓴다 — 처음에 `BinPickingReporter`로
    #    지어 썼다가 AttributeError로 죽었다(시그니처 추측 금지 계열, 8번째).
    #    ⭐ 다만 크게 실패해서 즉시 잡혔다 = "조용히 틀리지 말라"가 작동한 사례.
    reporter = WR.WebReporter(transport)
    res = reporter.report_bin_picking(six, latency_ms=latency_ms)
    return {"ok": bool(res), "target": where,
            "error": getattr(res, "error", None),
            "detail": getattr(res, "detail", None)}


def run_one(depth: Path, ckpt: Path, out_dir: Path, *, python: str,
            web_url: Optional[str]) -> dict:
    """depth 1장을 끝까지. 반환 = 사람이 읽을 요약 dict."""
    t0 = time.perf_counter()
    pred = step_infer(depth, ckpt, out_dir, python=python)
    six_path = step_six(pred, depth, out_dir, python=python)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    six = json.loads(six_path.read_text())
    dets = six.get("detections") or []
    gate = six.get("gate_summary") or {}
    scene = six.get("gate_scene") or {}
    rep = step_report(six_path, web_url=web_url, out_dir=out_dir, latency_ms=latency_ms)

    return {
        "depth": depth.name,
        "n_detections": len(dets),
        "labels": [d.get("label") for d in dets],
        "gate_dropped": gate.get("n_dropped"),
        "excluded_dropped": gate.get("excluded_parts_dropped"),
        "scene_verdict": scene.get("verdict"),
        "scene_valid_pct": scene.get("valid_ratio_pct"),
        "latency_ms": round(latency_ms, 1),
        "six_json": str(six_path),
        "web": rep,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--depth", type=Path, help="depth .npy 1장")
    g.add_argument("--depth-dir", type=Path, help="depth .npy 디렉토리")
    ap.add_argument("--glob", default="shot*.npy", help="--depth-dir 용 패턴")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, default=None,
                    help=f"기본 = {DEFAULT_CKPT}")
    ap.add_argument("--web-url", default=None,
                    help="빈피킹 수신 엔드포인트. 생략하면 파일로만 남긴다(서버 없이 검증)")
    ap.add_argument("--python", default=sys.executable,
                    help="추론에 쓸 파이썬(torch가 있는 것). 기본 = 현재 인터프리터")
    args = ap.parse_args()

    ckpt = _find_checkpoint(args.checkpoint)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    files = [args.depth] if args.depth else sorted(args.depth_dir.glob(args.glob))
    if not files:
        raise E2EError(f"[입력] depth 파일이 없다: {args.depth_dir}/{args.glob}")

    print(f"체크포인트 = {ckpt}")
    print(f"추론 플래그 = {' '.join(INFER_FLAGS)}")
    print(f"웹 대상    = {args.web_url or '(파일 출력)'}")
    print(f"대상 {len(files)}장\n")

    rows, failed = [], 0
    for i, dp in enumerate(files, 1):
        try:
            r = run_one(dp, ckpt, args.out_dir, python=args.python, web_url=args.web_url)
        except E2EError as exc:
            failed += 1
            print(f"[{i}/{len(files)}] 🔴 {dp.name}\n{exc}\n")
            continue
        rows.append(r)
        # 🚨 개수만 보지 말 것 — 8/14 교훈. 부품 이름을 함께 찍는다.
        names = ", ".join(str(x) for x in r["labels"][:4]) or "(없음)"
        web = "✅" if r["web"]["ok"] else f"🔴{r['web']['error']}"
        print(f"[{i}/{len(files)}] {dp.name}: 검출 {r['n_detections']}건 "
              f"[{names}] · 장면 {r['scene_verdict']}({r['scene_valid_pct']}%) "
              f"· 게이트 -{r['gate_dropped']}(제외종 -{r['excluded_dropped']}) "
              f"· {r['latency_ms']}ms · 웹 {web}")

    summary = {
        "n_input": len(files), "n_ok": len(rows), "n_failed": failed,
        "checkpoint": str(ckpt), "infer_flags": INFER_FLAGS,
        "web_url": args.web_url,
        "total_detections": sum(r["n_detections"] for r in rows),
        "web_ok": sum(1 for r in rows if r["web"]["ok"]),
        "rows": rows,
    }
    sp = args.out_dir / "e2e_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"\n{'='*70}")
    print(f"성공 {len(rows)}/{len(files)} · 검출 합계 {summary['total_detections']}건 "
          f"· 웹 성공 {summary['web_ok']}/{len(rows)}")
    print(f"요약 = {sp}")
    print("="*70)
    return 1 if failed else 0


if __name__ == "__main__":
    # 🚨 Windows(cp949)에서 이모지 print가 UnicodeEncodeError로 죽는 것을 막는다
    #    (8/28 IPC 실사고) → utils/console_utf8.py
    try:
        from bin_picking.src.utils.console_utf8 import enable_utf8_console

        enable_utf8_console()
    except Exception:
        pass
    try:
        sys.exit(main())
    except E2EError as exc:
        print(f"\n🔴 {exc}", file=sys.stderr)
        sys.exit(2)
