#!/usr/bin/env python3
"""환경 지문 — "같은 조건"이 진짜 같은지 파일로 남긴다.

🚨🚨 왜 필요한가 (8/21 실측 사고)
   A100 평가기가 **7/6자**로 낡아 8/19 동치 처리가 빠져 있었고,
   c2 기준선이 **0.0985 → 0.1281**로 바뀌면서 *"C만 동반 상승"* 근거가 무너졌다.
   찾아가는 순서가 **md5(데이터·라벨 동일) → 플래그(동일) → 코드**였고
   **코드에서 갈렸다.**
   ⇒ ⭐⭐ **"같은 조건"에는 코드 버전과 패키지 버전이 들어간다.**

⭐ 8/21에 평가기가 자기 `evaluator_sha256`를 결과에 남기게 한 것과 같은 계열이다.
   이 스크립트는 그것을 **E2E 러너 쪽에** 붙인다.

사용법:
    python emit_env_fingerprint.py --out <out-dir>/env.json
    python emit_env_fingerprint.py --out env.json --ckpt bin_picking/models/T100_best.pt
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def pkg_version(name, import_as=None):
    try:
        m = __import__(import_as or name)
        return getattr(m, "__version__", "?")
    except Exception as e:
        return f"🔴 {type(e).__name__}"


def git_head(repo):
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt", default="bin_picking/models/T100_best.pt")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()

    fp = {
        "host": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),          # 🚨 x86_64 vs aarch64 — Thor 이식 때 핵심
        "python": sys.version.split()[0],
        "git_head": git_head(args.repo),
    }

    # 🚨 실측 의존성 5개 (import 전수 추출로 확인 — requirements.txt를 믿지 않는다)
    for name, imp in (("numpy", None), ("torch", None), ("pillow", "PIL"),
                      ("opencv", "cv2"), ("pyyaml", "yaml")):
        fp[f"pkg.{name}"] = pkg_version(name, imp)

    # torch 세부 — CPU/CUDA 조합이 다르면 수치가 갈릴 수 있다
    try:
        import torch
        fp["torch.cuda_available"] = bool(torch.cuda.is_available())
        fp["torch.device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
    except Exception:
        pass

    # ⭐ 체크포인트 md5 — "ckpt가 로드는 되는데 값이 이상"할 때 이것부터 본다
    ck = Path(args.ckpt)
    if ck.exists():
        fp["ckpt.path"] = str(ck)
        fp["ckpt.md5"] = md5(ck)
        fp["ckpt.bytes"] = ck.stat().st_size
    else:
        fp["ckpt.md5"] = f"🔴 없음: {ck}"

    # 추론 스크립트·전처리 sha256 — 8/21 "코드에서 갈렸다"를 잡는 자리
    # 🚨 경로는 실측으로 확인했다 — 전처리·모델·후처리는 `mentoring_new/depth_vq_detector/`
    #    하위에 있고, `infer_depth_vq_detector.py:11`이 그쪽을 import 한다.
    #    (`depth_track/model/` 아래에도 같은 이름 파일이 있으나 추론이 쓰는 것은 이쪽이다)
    MENT = "bin_picking/depth_track/mentoring_new"
    for label, rel in (("infer", f"{MENT}/infer_depth_vq_detector.py"),
                       ("preprocess", f"{MENT}/depth_vq_detector/depth_preprocess.py"),
                       ("model", f"{MENT}/depth_vq_detector/model.py"),
                       ("postprocess", f"{MENT}/depth_vq_detector/postprocess.py"),
                       ("six", "bin_picking/src/pipeline/depth_track_to_6elements.py"),
                       ("gate", "bin_picking/src/pipeline/input_gate.py")):
        p = Path(args.repo) / rel
        if p.exists():
            fp[f"code.{label}.sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        else:
            fp[f"code.{label}.sha256"] = "🔴 없음"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fp, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"환경 지문 → {out}\n")
    for k, v in fp.items():
        print(f"  {k:28s} {v}")
    print("\n⭐ 두 서버에서 각각 만들어 `compare_e2e_results.py`가 비교한다.")
    print("🚨 `machine`이 다르면(x86_64 ↔ aarch64) 수치 차이는 이식 오류가 아닐 수 있다 —")
    print("   그때는 좌표·이름이 같은지를 우선 본다.")


if __name__ == "__main__":
    main()
