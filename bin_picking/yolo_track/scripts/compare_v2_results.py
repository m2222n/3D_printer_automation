"""
v2 비교 학습 결과 분석 스크립트 (5/20)
=========================================

train_v2_comparison.sh가 5개 모델 학습 완료 후 자동 호출.
각 모델의 results.csv를 읽어서 비교 표 + 마크다운 요약 생성.

사용:
    python compare_v2_results.py --runs-dir /workspace/binpicking_yolo/runs/v2-comparison

출력:
    1. stdout: 정렬된 비교 표
    2. {runs-dir}/v2_comparison_summary.md: 마크다운 보고서
    3. {runs-dir}/v2_comparison.csv: CSV (스프레드시트용)
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional


# 5개 모델 정보 (train_v2_comparison.sh와 동기화)
MODEL_INFO = {
    "yolov8n": {"params_M": 3.2, "version": "v8", "size": "nano"},
    "yolov8m": {"params_M": 25.9, "version": "v8", "size": "medium"},
    "yolo11s": {"params_M": 9.5, "version": "v11", "size": "small"},
    "yolo11m": {"params_M": 20.1, "version": "v11", "size": "medium"},
    "yolo11l": {"params_M": 25.3, "version": "v11", "size": "large"},
}


def parse_results_csv(csv_path: Path) -> Optional[dict]:
    """results.csv의 마지막 행 + best epoch을 파싱."""
    if not csv_path.exists():
        return None
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    # 컬럼명 공백 제거
    rows = [{k.strip(): v.strip() for k, v in r.items()} for r in rows]
    last = rows[-1]
    # mAP50 기준 best epoch
    map50_key = next((k for k in last.keys() if "metrics/mAP50" in k and "mAP50-95" not in k), None)
    map5095_key = next((k for k in last.keys() if "metrics/mAP50-95" in k), None)
    precision_key = next((k for k in last.keys() if "metrics/precision" in k), None)
    recall_key = next((k for k in last.keys() if "metrics/recall" in k), None)

    if not map50_key:
        return None

    best_idx = max(range(len(rows)), key=lambda i: float(rows[i].get(map50_key, "0") or "0"))
    best = rows[best_idx]

    return {
        "epochs_trained": len(rows),
        "best_epoch": int(best.get("epoch", best_idx + 1)),
        "best_mAP50": float(best.get(map50_key, "0") or "0"),
        "best_mAP50-95": float(best.get(map5095_key, "0") or "0") if map5095_key else 0.0,
        "best_precision": float(best.get(precision_key, "0") or "0") if precision_key else 0.0,
        "best_recall": float(best.get(recall_key, "0") or "0") if recall_key else 0.0,
        "final_mAP50": float(last.get(map50_key, "0") or "0"),
        "final_mAP50-95": float(last.get(map5095_key, "0") or "0") if map5095_key else 0.0,
    }


def collect_results(runs_dir: Path) -> list[dict]:
    """runs_dir 아래 v2-{model}/results.csv 5개 수집."""
    results = []
    for model_name, info in MODEL_INFO.items():
        run_dir = runs_dir / f"v2-{model_name}"
        csv_path = run_dir / "results.csv"
        weights_dir = run_dir / "weights"
        best_pt = weights_dir / "best.pt"

        metrics = parse_results_csv(csv_path)
        if metrics is None:
            results.append({
                "model": model_name,
                "params_M": info["params_M"],
                "version": info["version"],
                "size": info["size"],
                "status": "NO_DATA",
                "run_dir": str(run_dir),
            })
            continue

        results.append({
            "model": model_name,
            "params_M": info["params_M"],
            "version": info["version"],
            "size": info["size"],
            "status": "OK" if best_pt.exists() else "INCOMPLETE",
            "run_dir": str(run_dir),
            "best_pt_size_MB": (best_pt.stat().st_size / 1e6) if best_pt.exists() else 0,
            **metrics,
        })
    return results


def print_comparison_table(results: list[dict]) -> None:
    """정렬된 비교 표 stdout 출력."""
    ok_results = [r for r in results if r["status"] == "OK"]
    if not ok_results:
        print("⚠️ 완료된 학습 결과 없음")
        return

    # mAP50 내림차순 정렬
    ok_results.sort(key=lambda r: r["best_mAP50"], reverse=True)

    print()
    print("=" * 100)
    print(f"  v2 비교 결과 (mAP50 내림차순)")
    print("=" * 100)
    print(f"{'Rank':<6}{'Model':<12}{'Params':<10}{'mAP50':<10}{'mAP50-95':<12}{'P':<8}{'R':<8}{'Best Ep':<10}")
    print("-" * 100)
    for rank, r in enumerate(ok_results, 1):
        emoji = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "  "))
        print(f"{emoji} {rank:<4}{r['model']:<12}"
              f"{r['params_M']:>5.1f}M  "
              f"{r['best_mAP50']:.4f}    "
              f"{r['best_mAP50-95']:.4f}      "
              f"{r['best_precision']:.3f}   "
              f"{r['best_recall']:.3f}   "
              f"{r['best_epoch']:>3}/{r['epochs_trained']}")
    print("=" * 100)
    print()

    failed = [r for r in results if r["status"] != "OK"]
    if failed:
        print(f"⚠️ 미완료 학습:")
        for r in failed:
            print(f"  - {r['model']}: {r['status']}")


def write_markdown_summary(results: list[dict], out_path: Path) -> None:
    """마크다운 비교 보고서 작성."""
    ok = [r for r in results if r["status"] == "OK"]
    ok.sort(key=lambda r: r["best_mAP50"], reverse=True)

    lines = [
        "# v2 5개 모델 비교 결과",
        "",
        f"학습 데이터셋: v2 (5/15 116장 + 5/18 62장 + 5/20 Part4 + 멀티)",
        f"학습 조건: epochs=200, imgsz=640, batch=16, cos_lr, patience=50",
        "",
        "## 결과 (mAP50 내림차순)",
        "",
        "| Rank | Model | Version | Size | Params | mAP50 | mAP50-95 | Precision | Recall | Best Epoch |",
        "|------|-------|---------|------|--------|-------|----------|-----------|--------|------------|",
    ]
    for rank, r in enumerate(ok, 1):
        emoji = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else ""))
        lines.append(
            f"| {emoji} {rank} | `{r['model']}` | {r['version']} | {r['size']} | "
            f"{r['params_M']:.1f}M | "
            f"**{r['best_mAP50']:.4f}** | {r['best_mAP50-95']:.4f} | "
            f"{r['best_precision']:.3f} | {r['best_recall']:.3f} | "
            f"{r['best_epoch']}/{r['epochs_trained']} |"
        )

    lines += [
        "",
        "## v1 baseline 비교 (5/18 학습)",
        "",
        "| Metric | v1 (yolov8n, 116장) | v2 best | 변화 |",
        "|--------|---------------------|---------|------|",
    ]
    v1_map50 = 0.988  # 5/18 결과
    if ok:
        best = ok[0]
        delta = best["best_mAP50"] - v1_map50
        delta_sign = "+" if delta >= 0 else ""
        lines.append(f"| mAP50 | {v1_map50:.4f} | **{best['best_mAP50']:.4f}** ({best['model']}) | {delta_sign}{delta:.4f} |")

    lines += [
        "",
        "## 미완료 학습",
        "",
    ]
    failed = [r for r in results if r["status"] != "OK"]
    if failed:
        for r in failed:
            lines.append(f"- `{r['model']}`: {r['status']}")
    else:
        lines.append("(없음 — 5개 모델 모두 완료)")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"📝 마크다운 보고서 저장: {out_path}")


def write_csv_summary(results: list[dict], out_path: Path) -> None:
    """CSV 비교 표 작성 (스프레드시트용)."""
    fields = [
        "rank", "model", "version", "size", "params_M", "status",
        "best_mAP50", "best_mAP50-95", "best_precision", "best_recall",
        "best_epoch", "epochs_trained", "best_pt_size_MB",
    ]
    ok = [r for r in results if r["status"] == "OK"]
    ok.sort(key=lambda r: r["best_mAP50"], reverse=True)
    for rank, r in enumerate(ok, 1):
        r["rank"] = rank

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ok + [r for r in results if r["status"] != "OK"])
    print(f"📊 CSV 저장: {out_path}")


def main():
    ap = argparse.ArgumentParser(description="v2 5개 모델 비교 결과 분석")
    ap.add_argument("--runs-dir", type=Path, required=True,
                    help="v2-comparison 디렉토리 (v2-{model}/ 하위 포함)")
    args = ap.parse_args()

    if not args.runs_dir.exists():
        print(f"❌ {args.runs_dir} 없음")
        return

    results = collect_results(args.runs_dir)
    print_comparison_table(results)
    write_markdown_summary(results, args.runs_dir / "v2_comparison_summary.md")
    write_csv_summary(results, args.runs_dir / "v2_comparison.csv")


if __name__ == "__main__":
    main()
