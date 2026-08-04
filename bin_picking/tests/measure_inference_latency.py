#!/usr/bin/env python3
"""추론 지연시간 측정 — 로봇 socketReadLine 10초 예산에 드는가?

⭐ 왜 필요한가
--------------
8/4에 만든 소켓 서버는 로봇 쪽 `socketReadLine(name, 10000)` = **10초 타임아웃**
안에 좌표를 보내야 한다(`pick_socket_server.py:14`). 그런데 CPU 추론이
**장당 약 3초**(7/29, 100장 5분)라 여유가 크지 않다.

🚨 7/29 수치를 그대로 쓰면 안 되는 이유 = **100장 배치 평균**이라
   ① 모델 로드(첫 1회) ② 워밍업(첫 추론이 느림) ③ 1장 단독 지연
   이 전부 평균에 묻혀 있다. **실제 운영은 1장씩**이라 이게 진짜 숫자다.

측정 구간 (운영 경로와 같은 순서)
---------------------------------
  [A] 모델 로드      — 1회성. 서버 起動 시 미리 해두면 예산에서 빠진다
  [B] 추론 1장       — infer_one (전처리·forward·후처리 포함)
  [C] 6요소 변환     — depth_track 예측 → (x,y,z,edge,angle,label)
  [D] 좌표 검증·인코딩 — pick_encoder 범위 검증

  운영 예산 = [B] + [C] + [D]   ([A]는 접속 전에 끝내둘 수 있음)
  ⚠️ 촬영(Blaze grab)은 카메라가 없어 측정 불가 → 별도 항목으로 남긴다

⭐ 콜드/웜 분리 = 첫 추론(워밍업 포함)과 이후를 따로 보고한다. torch CPU는
   첫 forward에서 커널 초기화가 일어나 유의미하게 느리다.

사용:
  PYTHONPATH=/home/jtm/3D_printer_automation /data/jtm/depth_venv/bin/python \
    bin_picking/tests/measure_inference_latency.py \
      --depth_dir /data/jtm/blaze_crosssession_0731 --n 10
"""
from __future__ import annotations
import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
MENTORING = HERE.parents[1] / "depth_track" / "mentoring_new"
sys.path.insert(0, str(MENTORING))

CKPT_DEFAULT = ("/data/jtm/a100_backup_0710/checkpoints/extracted/runs/"
                "T100_csblur_lr1e4_ep80/best.pt")

ROBOT_TIMEOUT_SEC = 10.0   # 로봇 socketReadLine 타임아웃


def _pct(vals, p):
    """p 백분위(선형보간 없이 보수적으로 위쪽 인덱스)."""
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))
    return s[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth_dir", required=True)
    ap.add_argument("--checkpoint", default=CKPT_DEFAULT)
    ap.add_argument("--glob", default="shot*.npy")
    ap.add_argument("--n", type=int, default=10, help="측정 장수")
    ap.add_argument("--threads", type=int, default=None,
                    help="torch CPU 스레드 수 고정(미지정=기본). IPC 비교 시 유용")
    ap.add_argument("--out", default=None, help="결과 JSON 경로")
    args = ap.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)

    depth_dir = Path(args.depth_dir)
    files = sorted(depth_dir.glob(args.glob))
    if not files:
        files = sorted((depth_dir / "npy").glob(args.glob))
    if not files:
        print(f"🔴 {args.glob} 없음: {args.depth_dir}")
        return 1
    files = files[:args.n]

    import eval_real_depth_vq_detector as E

    print("=" * 68)
    print("추론 지연시간 측정 — 로봇 10초 예산 대조")
    print("=" * 68)
    print(f"장수 {len(files)} / torch {torch.__version__} / "
          f"threads {torch.get_num_threads()}")
    print(f"체크포인트 {Path(args.checkpoint).name}\n")

    # ---- [A] 모델 로드 (1회성) --------------------------------------
    t0 = time.perf_counter()
    (model, device, ckpt_args, input_mode, image_size,
     label_offset, cad_ids) = E.load_model_from_checkpoint(args.checkpoint, "cpu")
    load_sec = time.perf_counter() - t0
    print(f"[A] 모델 로드        {load_sec:7.3f}s  (1회성 — 접속 전 완료 가능)\n")

    # 6요소 변환 + 포즈 변환 모듈 (운영 경로와 동일하게 import)
    from bin_picking.src.pipeline import depth_track_to_6elements as SIX
    from bin_picking.src.communication import pick_socket_server as SOCK

    infer_t, six_t, enc_t, n_preds = [], [], [], []

    for i, f in enumerate(files, 1):
        # ---- [B] 추론 1장 -------------------------------------------
        t0 = time.perf_counter()
        inf = E.infer_one(
            model=model, device=device, depth_path=f,
            input_mode=input_mode, image_size=image_size,
            label_offset=label_offset, cad_ids=cad_ids,
            camera_path=None,
            # 🔴 10.0이 기본값 — None을 넘기면 검출이 무너진다(7/30 버그)
            real_uint16_max_depth_m=10.0, depth_scale=None, zero_to_nan=False,
            center_keep=None, center_crop="1/6,5/6",
            depth_keep_range="0.40,0.60", infer_avg_pool_kernel=1,
            score_thresh=0.45, mask_thresh=0.5,
            topk=100, score_mode="det",
            nms_iou_thresh=0.5, nms_iou_type="mask",
            bbox_source="mask",
        )
        dt_infer = time.perf_counter() - t0

        # ---- [C] 6요소 변환 -----------------------------------------
        # ⚠️ convert()는 depth **배열**을 받는다(경로 아님). 운영에서도 촬영한
        #    배열을 그대로 넘기므로 load 시간은 예산 밖(촬영 항목)으로 둔다.
        depth_arr = np.load(f)
        t0 = time.perf_counter()
        six = SIX.convert(inf, depth=depth_arr)
        dt_six = time.perf_counter() - t0

        # ---- [D] 6요소 → 포즈 변환 + 범위 검증 ----------------------
        # ⭐ 운영 경로와 동일하게 소켓 서버의 함수를 쓴다(pick_encoder 직접 호출
        #    아님 — INT16 인코딩은 8/4에 폐기됐고 지금은 포즈 검증만 한다).
        t0 = time.perf_counter()
        ok = 0
        for det in six.get("detections", []):
            try:
                SOCK.six_elements_to_pose(det)
                ok += 1
            except Exception:
                pass   # 거부는 정상 동작(신뢰불가 angle 등) — 건별 필터링
        dt_enc = time.perf_counter() - t0

        infer_t.append(dt_infer)
        six_t.append(dt_six)
        enc_t.append(dt_enc)
        n = len(inf.get("predictions") or [])
        n_preds.append(n)

        total = dt_infer + dt_six + dt_enc
        tag = "  ← 콜드(워밍업 포함)" if i == 1 else ""
        print(f"[{i:02d}/{len(files):02d}] {f.name:24s} "
              f"추론 {dt_infer:6.3f}s + 6요소 {dt_six:6.3f}s "
              f"+ 검증 {dt_enc:5.3f}s = {total:6.3f}s  (검출 {n:2d}){tag}")

    # ---- 요약 --------------------------------------------------------
    warm_infer = infer_t[1:] or infer_t
    warm_total = [infer_t[i] + six_t[i] + enc_t[i]
                  for i in range(1, len(infer_t))] or \
                 [infer_t[0] + six_t[0] + enc_t[0]]

    print("\n" + "=" * 68)
    print("요약")
    print("=" * 68)
    print(f"[A] 모델 로드 (1회성)      {load_sec:7.3f}s")
    print(f"[B] 추론    콜드 1장       {infer_t[0]:7.3f}s")
    print(f"           웜 평균         {st.mean(warm_infer):7.3f}s"
          f"   중앙 {st.median(warm_infer):6.3f}s"
          f"   최대 {max(warm_infer):6.3f}s")
    print(f"[C] 6요소 변환 평균        {st.mean(six_t):7.3f}s")
    print(f"[D] 검증 평균              {st.mean(enc_t):7.3f}s")
    print("-" * 68)
    p95 = _pct(warm_total, 95)
    print(f"운영 예산 [B+C+D] 웜 평균  {st.mean(warm_total):7.3f}s")
    print(f"                   최대     {max(warm_total):7.3f}s")
    print(f"                   p95      {p95:7.3f}s")
    print(f"검출 장당 평균             {st.mean(n_preds):7.2f}건")
    print("-" * 68)

    worst = max(warm_total)
    margin = ROBOT_TIMEOUT_SEC - worst
    print(f"로봇 타임아웃 예산         {ROBOT_TIMEOUT_SEC:7.3f}s")
    print(f"최악 대비 여유             {margin:7.3f}s "
          f"({margin / ROBOT_TIMEOUT_SEC * 100:.0f}%)")
    if margin < 0:
        verdict = "🔴 초과 — 설계 변경 필수"
    elif margin < 3.0:
        verdict = "🟡 경계 — 촬영시간 미포함이라 위험"
    else:
        verdict = "🟢 여유 있음"
    print(f"판정                       {verdict}")
    print("=" * 68)
    print("⚠️ 미포함 = Blaze 촬영(grab) 시간. 카메라 없어 측정 불가.")
    print("⚠️ 이 수치는 6000 서버 CPU 기준. IPC-510 CPU는 [미확인]이라")
    print("   더 느릴 수 있음 → 내일 스펙 확인 후 재측정 필요.")

    if args.out:
        payload = {
            "host_torch": torch.__version__,
            "threads": torch.get_num_threads(),
            "n_frames": len(files),
            "model_load_sec": load_sec,
            "infer_cold_sec": infer_t[0],
            "infer_warm_mean_sec": st.mean(warm_infer),
            "infer_warm_max_sec": max(warm_infer),
            "six_mean_sec": st.mean(six_t),
            "enc_mean_sec": st.mean(enc_t),
            "budget_warm_mean_sec": st.mean(warm_total),
            "budget_warm_max_sec": worst,
            "budget_warm_p95_sec": p95,
            "robot_timeout_sec": ROBOT_TIMEOUT_SEC,
            "margin_sec": margin,
            "verdict": verdict,
            "per_frame": [
                {"file": f.name, "infer": infer_t[i], "six": six_t[i],
                 "enc": enc_t[i], "n_pred": n_preds[i]}
                for i, f in enumerate(files)
            ],
        }
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        print(f"\n결과 저장 → {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
