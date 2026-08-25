"""배치 추론 러너 — 모델을 **한 번만** 로드해 여러 장을 처리한다.

🎯 목적 = KTR 정량목표 2번(**통합 모니터링 응답속도 3초 이내**)
   `run_binpick_e2e.py`가 장당 `subprocess`를 띄워 **매번 파이썬·torch·모델을
   다시 로드**한다. 그 재로드분을 없앤다.

⭐⭐ 8/25 실측으로 지연을 갈랐다 (6000 CPU · `shot_001_c1.npy`)

  | 구간 | 시간 | 상주로 없앨 수 있나 |
  |---|---|---|
  | 파이썬 + torch/cv2/PIL import | **1.00초** | ✅ |
  | 모델 준비(torch.load 0.03 + 생성 0.26 + state_dict 0.41) | **0.70초** | ✅ |
  | **순수 forward (CPU)** | **1.85~2.01초** | 🔴 **못 없앤다** |
  | 전처리·후처리·저장 | ~0.5초 | 부분적 |
  | **전체** | **4.18초** | |

🚨🚨 **실측 결과 = 4.27 → 3.44초 (18% 개선). 내 기대값 2.4초는 틀렸다.**

  cProfile 로 3.20초를 갈라보니:

  | 구간 | 시간 | 비중 |
  |---|---|---|
  | **모델 forward** | **1.92초** (transformer 0.78 + conv 0.61) | **60%** |
  | **postprocess** | **0.57초** | 18% |
  | 전처리·저장 등 | ~0.7초 | 22% |

  ⇒ ⭐⭐ **재로드를 없애도 3.4초에서 멈춘다. forward 가 벽이다.**
  📌 **결론 = 상주 프로세스는 KTR 3초의 해법이 아니다(절반도 아니다).**
     🥇 **본해법은 GPU** — IPC 에 RTX 5060 이 있는데 torch 가 `+cpu` 빌드라
     안 쓰고 있다. CUDA 빌드로 바꾸면 forward 1.92초가 크게 준다.
  ⚠️ **[미확인]** GPU 에서 몇 초가 되는지는 재보지 않았다(6000 에 GPU 없음).

  ⭐ 그래도 이 파일은 남긴다 = ①0.83초는 실제로 줄었다 ②IPC/Thor 이식 때
  **같은 값이 나오는지 대조하는 경로**가 되고 ③GPU 전환 후 재측정의 기준이 된다.

🚨🚨 왜 추론기를 리팩터링하지 않았나 (중요한 설계 판단)
   `infer_depth_vq_detector.py`의 `main()`은 **모델 로드 → 단일 장면 처리**가
   한 함수에 이어져 있다. 함수를 쪼개면 배치가 자연스럽지만 **그 코드는
   8/21에 "검증된 추론 경로"로 못박은 것**이고, 손대면 값이 바뀔 위험이 있다.
   (8/14 = 플래그 하나로 부품 이름이 바뀌었다 / 8/21 = 평가기 코드가 갈려
    c2 기준선이 무너졌다)
   ⇒ 📌 **원본을 한 줄도 고치지 않는다.** `torch.load`를 프로세스 안에서
      캐싱하고 `sys.argv`를 바꿔가며 `main()`을 반복 호출한다.
   ⭐ 그래서 **결과가 기존과 완전히 같아야 하고, 그것을 대조로 증명한다.**

⚠️ 한계
   - 프로세스 하나에서 순차 처리다(진짜 상주 서버는 아니다). 소켓 대기까지
     가는 것은 **IPC에서 실물을 보고** 결정한다.
   - `main()`이 `SystemExit`를 던지면 그 장만 실패로 기록하고 계속 간다.

사용법:
    python bin_picking/src/infer_batch_runner.py \
        --depth-dir /data/jtm/synth_out/blaze_capture_0818 \
        --glob "shot_00[1-5]_c1.npy" --out-dir /tmp/batch5

    # 기존 경로와 값이 같은지 대조
    python bin_picking/depth_track/scripts/compare_e2e_results.py \
        --ref /data/jtm/e2e_reference_0825 --test /tmp/batch5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MENTORING = REPO / "bin_picking" / "depth_track" / "mentoring_new"
DEFAULT_CKPT = REPO / "bin_picking" / "models" / "T100_best.pt"

# ⭐⭐ 검증된 추론 플래그 — `run_binpick_e2e.py`와 **완전히 같은 값**이어야 한다.
# 🚨 여기가 갈리면 배치 결과가 기준선과 달라지는데 원인을 찾기 어렵다.
INFER_FLAGS = [
    "--real_uint16_max_depth_m", "10.0",
    "--center_crop", "1/6,5/6",
    "--depth_keep_range", "0.40,0.60",
    "--score_thresh", "0.20",
    "--mask_thresh", "0.5",
    "--score_mode", "det",
]


class BatchError(RuntimeError):
    pass


def _install_ckpt_cache():
    """`torch.load`를 감싸 **같은 체크포인트를 두 번 읽지 않게** 한다.

    🚨 왜 deepcopy 하지 않나 = 체크포인트 dict 는 `main()` 안에서 **읽기만** 한다
       (`ckpt.get(...)` · `load_state_dict(ckpt["model"])`). 복사하면 70MB를
       매번 복제해 오히려 느려진다.
    ⚠️ 만약 나중에 `main()`이 ckpt 를 수정하게 되면 이 가정이 깨진다 —
       그때는 결과 대조가 먼저 틀어지므로 **대조가 방어선 역할을 한다.**
    """
    import torch

    original = torch.load
    cache: dict = {}

    def cached_load(f, *a, **kw):
        key = str(f)
        if key in cache:
            return cache[key]
        obj = original(f, *a, **kw)
        # 체크포인트로 보이는 것만 캐싱한다(경로 문자열 + dict 결과)
        if isinstance(obj, dict) and "model" in obj:
            cache[key] = obj
        return obj

    torch.load = cached_load
    return cache


def run_batch(depths, ckpt: Path, out_dir: Path):
    """모델을 한 번만 로드해 여러 장을 추론한다. 장별 (성공, 소요ms)."""
    sys.path.insert(0, str(MENTORING))
    import os

    cwd0 = os.getcwd()
    os.chdir(MENTORING)                     # 추론기가 상대 import 를 쓴다
    try:
        cache = _install_ckpt_cache()
        t_imp = time.perf_counter()
        from infer_depth_vq_detector import main as infer_main
        imp_ms = (time.perf_counter() - t_imp) * 1000.0

        results = []
        argv0 = sys.argv[:]
        for i, d in enumerate(depths, 1):
            pred_dir = out_dir / "pred" / d.stem
            pred_dir.mkdir(parents=True, exist_ok=True)
            sys.argv = ["infer_depth_vq_detector.py",
                        "--checkpoint", str(ckpt),
                        "--depth", str(d),
                        "--out_dir", str(pred_dir)] + INFER_FLAGS
            t0 = time.perf_counter()
            ok, err = True, None
            try:
                infer_main()
            except SystemExit as e:          # argparse/에러 종료
                if e.code not in (0, None):
                    ok, err = False, f"SystemExit {e.code}"
            except Exception as e:           # noqa: BLE001 — 한 장 실패가 전체를 죽이지 않게
                ok, err = False, f"{type(e).__name__}: {e}"
            ms = (time.perf_counter() - t0) * 1000.0
            cached = len(cache)
            print(f"  [{i}/{len(depths)}] {d.name}  {ms:7.0f}ms"
                  f"  {'🟢' if ok else '🔴 ' + str(err)}"
                  f"{'  (모델 재사용)' if cached and i > 1 else ''}")
            results.append({"depth": str(d), "ok": ok, "ms": round(ms, 1), "error": err})
        sys.argv = argv0
        return results, imp_ms
    finally:
        os.chdir(cwd0)


def to_six(pred_json: Path, depth: Path, out_dir: Path, python: str) -> Path | None:
    """6요소 + 게이트 — `run_binpick_e2e.py`와 같은 방식(subprocess)으로 부른다.

    ⭐ 여기는 torch 를 쓰지 않아 재로드 비용이 작다. 같은 모듈을 같은 인자로
       부르므로 **결과가 기존과 같아야 한다.**
    """
    six_dir = out_dir / "six"
    six_dir.mkdir(parents=True, exist_ok=True)
    six_path = six_dir / f"{depth.stem}.six.json"
    cmd = [python, "-m", "bin_picking.src.pipeline.depth_track_to_6elements",
           "--pred", str(pred_json), "--out", str(six_path),
           "--depth-dir", str(depth.parent)]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  🔴 6요소 실패 {depth.name}: {r.stderr.strip()[-300:]}")
        return None
    return six_path if six_path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description="배치 추론 — 모델 1회 로드")
    ap.add_argument("--depth-dir", required=True)
    ap.add_argument("--glob", default="shot*.npy")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--no-six", action="store_true", help="6요소 변환 생략(추론만 측정)")
    args = ap.parse_args()

    ckpt = Path(args.checkpoint) if args.checkpoint else DEFAULT_CKPT
    if not ckpt.exists():
        raise BatchError(
            f"[체크포인트] 없다: {ckpt}\n"
            "  → 6000 /data/jtm/a100_backup_0710/.../T100_csblur_lr1e4_ep80/best.pt\n"
            "  🚨 md5 afcf73511be501ebd813a08bd91a1b65 로 대조할 것"
        )
    depths = sorted(Path(args.depth_dir).glob(args.glob))
    if not depths:
        raise BatchError(f"[입력] {args.glob} 를 못 찾음: {args.depth_dir}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"체크포인트 = {ckpt}")
    print(f"추론 플래그 = {' '.join(INFER_FLAGS)}")
    print(f"대상 {len(depths)}장 · 모델 1회 로드\n")

    t_all = time.perf_counter()
    results, imp_ms = run_batch(depths, ckpt, out_dir)
    infer_s = time.perf_counter() - t_all

    six_paths = []
    if not args.no_six:
        print()
        for d in depths:
            pdir = out_dir / "pred" / d.stem
            cands = sorted(pdir.glob(f"{d.stem}*.json")) or sorted(pdir.glob("*.json"))
            if not cands:
                print(f"  🔴 예측 JSON 없음: {d.name}")
                continue
            sp = to_six(cands[-1], d, out_dir, args.python)
            if sp:
                six_paths.append(sp)
        print(f"  6요소 {len(six_paths)}/{len(depths)}장")

    total_s = time.perf_counter() - t_all
    okn = sum(1 for r in results if r["ok"])
    per = [r["ms"] for r in results if r["ok"]]

    print("\n" + "=" * 62)
    print(f"  성공 {okn}/{len(depths)}")
    if per:
        print(f"  추론 장당   최초 {per[0]:.0f}ms · 이후 평균 "
              f"{(sum(per[1:]) / len(per[1:])):.0f}ms" if len(per) > 1
              else f"  추론 장당 {per[0]:.0f}ms")
        print(f"  추론 합계   {infer_s:.2f}초")
    print(f"  전체(6요소 포함) {total_s:.2f}초 · 장당 {total_s / len(depths):.2f}초")
    print(f"  ⭐ 비교 = `run_binpick_e2e.py` 장당 4.27~4.57초 (8/25 6000 실측)")
    print("  🚨 KTR 3초 판정은 **전체 응답**으로 해야 한다 — 촬영·전송 포함 여부 확인 필요")
    print("=" * 62)

    (out_dir / "batch_summary.json").write_text(json.dumps({
        "n": len(depths), "ok": okn,
        "import_ms": round(imp_ms, 1),
        "infer_seconds": round(infer_s, 2),
        "total_seconds": round(total_s, 2),
        "per_shot_seconds": round(total_s / len(depths), 3),
        "results": results,
        "note": "모델 1회 로드. 값이 기존과 같은지는 compare_e2e_results.py 로 대조한다",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n⏭️ 값 대조:")
    print(f"   python bin_picking/depth_track/scripts/compare_e2e_results.py \\")
    print(f"     --ref /data/jtm/e2e_reference_0825 --test {out_dir}")
    return 0 if okn == len(depths) else 1


if __name__ == "__main__":
    sys.exit(main())
