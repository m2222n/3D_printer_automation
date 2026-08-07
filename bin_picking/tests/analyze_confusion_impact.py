#!/usr/bin/env python3
"""혼동이 **파지에 실제로 무엇을 하는가**를 실측으로 집계한다. (2026-08-07)

⭐ 왜 이 도구가 필요한가
------------------------
8/5 cross-session 실측에서 c1 **종류 정답률 48.5%** 가 나왔고, 그 숫자가 그대로
사업 성과 지표처럼 읽히고 있다. 그런데 **"종류를 틀렸다"와 "부품을 못 집는다"는
같은 말이 아니다.**

  - `label`은 좌표에 쓰이지 않는다. 좌표(x,y,z)는 **위치**에서 나오고 위치
    precision은 **0.971**이다(8/5 실측).
  - `label`이 결정하는 것은 **그리퍼 벌림 하나뿐**이다(`grasp_plan.py`).
  - ⭐ 그러므로 혼동의 진짜 비용은 **"틀린 라벨의 벌림으로 집었을 때 잡히는가"** 다.

8/5에 상위 17건을 손으로 훑어 *"치명 2건 / 경미 14건 / 무해 1건"* 이라 적어두었으나
**전수 집계도, 재현 가능한 코드도 없었다.** 이 파일이 그것을 코드로 만든다.

🚨 판정 규칙 = 방향이 결과를 가른다 (8/5에 내가 한 번 틀렸던 지점)
------------------------------------------------------------------
벌림이 **작으면** 물리적으로 안 들어간다 → **치명**.
벌림이 **크면** 헐겁게라도 잡힌다 → **경미**.
내 1차 판정은 방향을 안 보고 "다르면 실패"로 세어 **과대평가**였다.

  used  = 예측 라벨의 벌림 (로봇이 실제로 벌릴 값)
  need  = GT 라벨의 벌림   (그 부품에 맞는 값)

  used < need - TIGHT_MM   → 🔴 치명 (안 들어감)
  used > need + LOOSE_MM   → 🟠 헐거움 (잡히나 미끄러질 수 있음)
  그 외                     → 🟢 무해 (오차 범위)

⚠️ 이 판정은 **DB 벌림값을 신뢰한다는 전제** 위에 있다. 8/6에 확인했듯
`gripper_width_mm`은 **방향이 섞여 작성돼 있어**(20종은 중간변+여유, 7종은 최소변+여유)
절대값은 티칭 때 실물로 교정해야 한다. 그래서 이 도구는 **"몇 mm 모자라다"가 아니라
"모자라는 쪽인가 남는 쪽인가"** 만 판정한다. 방향은 값이 흔들려도 유지된다.

사용법:
    python tests/analyze_confusion_impact.py
    python tests/analyze_confusion_impact.py --cond c1 --json out.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BIN_PICKING = REPO / "bin_picking"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_METRICS = Path(
    "/data/jtm/synth_out/reports/crosssession_30shot_eval_0805/eval_real_metrics.json")
DEFAULT_DB = BIN_PICKING / "config" / "grasp_database.yaml"

# ── 판정 임계 (mm) ──
# 🚨 추측값이 아니라 "판정 성격"에서 온 값이다.
#   TIGHT: 벌림이 이만큼 모자라면 조우가 부품에 걸려 진입하지 못한다.
#   LOOSE: 이만큼 남으면 부품이 조우 사이에서 흔들린다.
# ⭐ 값 자체보다 **방향**이 결론을 만든다(위 주석 참조). --tight/--loose로 흔들어
#   결론이 바뀌는지 확인할 수 있게 인자화했다.
TIGHT_MM = 2.0
LOOSE_MM = 15.0

# 🚨 `[^|]*` 이지 `(.+?)`가 아니다 — 8/7에 이 한 글자로 조용히 틀렸다.
#   `gt=`가 **빈 문자열**인 쌍이 있다(`__ignore__` 라벨. canonical 이름이 "__" 앞을
#   잘라 빈 문자열이 되는 기존 이슈). `.+?`는 1글자 이상을 요구해 그 줄을 **통째로
#   건너뛰었고**, 그 결과 분모가 68→67로 줄어 종류 정답률이 48.5%가 아닌 49.3%로
#   나왔다. ⭐**"파싱이 실패했다"가 아니라 "조용히 한 건 적게 세었다"** = 가장 위험한 종류.
#   → 지금은 빈 라벨도 잡아서 `unknown`(판정 불가)으로 **명시적으로 남긴다.**
PAIR_RE = re.compile(r"pred=([^|]*)\|gt=([^|]*)\|iou=([\d.]+)\|ok=(\d)")

VERDICT_FATAL = "fatal"
VERDICT_LOOSE = "loose"
VERDICT_OK = "harmless"
VERDICT_UNKNOWN = "unknown"


class ConfusionImpactError(RuntimeError):
    pass


def load_db(path: Path = DEFAULT_DB) -> dict:
    """그래스프 DB를 읽는다. 🚨없으면 폴백하지 않고 예외 — 조용히 틀리지 않는다."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 환경 문제
        raise ConfusionImpactError(
            "PyYAML이 없다. depth_venv로 실행할 것") from exc
    if not path.exists():
        raise ConfusionImpactError(f"그래스프 DB 없음: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parts = data.get("parts") or {}
    if not parts:
        raise ConfusionImpactError(f"DB에 parts가 비어 있다: {path}")
    return data


def width_of(db: dict, label: str) -> Optional[float]:
    """그 라벨로 로봇이 벌릴 값. 없으면 None(판정 불가로 남긴다).

    ⚠️ 빈 라벨(`__ignore__` 유래)도 None → `unknown`으로 흘러간다. 무해로 세지 않는다.
    """
    if not label:
        return None
    parts = db.get("parts") or {}
    entry = parts.get(label)
    if entry is None:
        return None
    w = entry.get("gripper_width_mm")
    if w is None:
        w = (db.get("defaults") or {}).get("gripper_width_mm")
    return None if w is None else float(w)


def parse_pairs(metrics: dict, cond: Optional[str] = None) -> list[dict]:
    """per_scene의 `spatial_pairs` 문자열을 (pred, gt) 쌍으로 푼다.

    ⭐ 위치가 맞은 검출만 들어 있다(spatial = 라벨 무시 매칭). 즉 여기 있는 쌍은
    **전부 "부품 위에 제대로 찍힌" 검출**이고, 남은 변수는 라벨뿐이다.

    🚨 **파싱 건수를 집계 필드와 대조한다.** 8/7에 정규식이 빈 라벨 줄을 조용히
    건너뛰어 분모가 1 작아진 적이 있다. 파싱은 "실패하면 티가 나는" 종류가 아니라
    **"조용히 덜 세는"** 종류라 대조가 유일한 방어다.
    """
    out: list[dict] = []
    expected = 0
    for scene in metrics.get("per_scene", []):
        fname = scene.get("file", "")
        if cond and not fname.endswith(f"_{cond}.npy"):
            continue
        expected += int(scene.get("spatial_tp_ignore_label", 0) or 0)
        raw = scene.get("spatial_pairs") or ""
        n_before = len(out)
        for m in PAIR_RE.finditer(raw):
            out.append({
                "scene": fname,
                "pred": m.group(1),
                "gt": m.group(2),
                "iou": float(m.group(3)),
                "label_ok": bool(int(m.group(4))),
            })
        # 장면 단위로도 대조해 어느 장면이 어긋났는지 바로 보이게 한다.
        got = len(out) - n_before
        exp_scene = int(scene.get("spatial_tp_ignore_label", 0) or 0)
        if got != exp_scene:
            raise ConfusionImpactError(
                f"파싱 건수 불일치: {fname} — 파싱 {got}건 vs spatial_tp {exp_scene}건. "
                f"정규식이 일부 줄을 건너뛰고 있다(빈 라벨 등). 분모가 틀어지므로 중단한다.")

    if len(out) != expected:
        raise ConfusionImpactError(
            f"파싱 총계 불일치: {len(out)}건 vs spatial_tp 합 {expected}건")
    return out


def judge(used: Optional[float], need: Optional[float],
          tight: float = TIGHT_MM, loose: float = LOOSE_MM) -> str:
    """벌림 방향으로 파지 결과를 판정한다.

    🚨 판정 못 하는 것은 무해로 세지 않는다 — 근거 없이 낙관하면 지표가 부풀려진다.
    """
    if used is None or need is None:
        return VERDICT_UNKNOWN
    if used < need - tight:
        return VERDICT_FATAL
    if used > need + loose:
        return VERDICT_LOOSE
    return VERDICT_OK


def analyze(pairs: list[dict], db: dict,
            tight: float = TIGHT_MM, loose: float = LOOSE_MM) -> dict:
    rows = []
    for p in pairs:
        if p["label_ok"]:
            verdict = VERDICT_OK  # 라벨이 맞으면 벌림도 맞다
            used = need = width_of(db, p["gt"])
        else:
            used = width_of(db, p["pred"])
            need = width_of(db, p["gt"])
            verdict = judge(used, need, tight, loose)
        rows.append({**p, "used_mm": used, "need_mm": need, "verdict": verdict})

    total = len(rows)
    vc = collections.Counter(r["verdict"] for r in rows)
    label_ok = sum(1 for r in rows if r["label_ok"])
    # ⭐ 핵심 지표 = "이 검출로 집었을 때 물리적으로 잡히는가"
    #    치명만 실패로 센다. 헐거움은 잡히긴 하므로 별도로 보고한다.
    graspable = total - vc[VERDICT_FATAL] - vc[VERDICT_UNKNOWN]

    confusions = collections.Counter(
        (r["gt"], r["pred"]) for r in rows if not r["label_ok"])
    fatal_pairs = collections.Counter(
        (r["gt"], r["pred"]) for r in rows if r["verdict"] == VERDICT_FATAL)

    return {
        "total_matched": total,
        "label_correct": label_ok,
        "label_acc": round(label_ok / total, 4) if total else 0.0,
        "graspable": graspable,
        "graspable_rate": round(graspable / total, 4) if total else 0.0,
        "verdicts": {
            "fatal": vc[VERDICT_FATAL],
            "loose": vc[VERDICT_LOOSE],
            "harmless": vc[VERDICT_OK],
            "unknown": vc[VERDICT_UNKNOWN],
        },
        "thresholds_mm": {"tight": tight, "loose": loose},
        "confusion_top": [
            {"gt": gt, "pred": pr, "n": n} for (gt, pr), n in confusions.most_common(15)
        ],
        "fatal_pairs": [
            {"gt": gt, "pred": pr, "n": n} for (gt, pr), n in fatal_pairs.most_common()
        ],
        "rows": rows,
    }


def sensitivity(pairs: list[dict], db: dict) -> list[dict]:
    """임계를 흔들어도 결론이 유지되는지 본다.

    ⭐ 8/6 파지 판정에서 배운 것 — 결론이 임계 하나에 매달려 있으면 근거가 약하다.
    """
    out = []
    for t in (0.0, 1.0, 2.0, 3.0, 5.0):
        r = analyze(pairs, db, tight=t, loose=LOOSE_MM)
        out.append({"tight_mm": t,
                    "fatal": r["verdicts"]["fatal"],
                    "graspable_rate": r["graspable_rate"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="혼동이 파지에 실제로 미치는 영향을 집계한다")
    ap.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--cond", default="c1",
                    help="조건 필터(c1/c2/c3). 빈 문자열이면 전체")
    ap.add_argument("--tight", type=float, default=TIGHT_MM)
    ap.add_argument("--loose", type=float, default=LOOSE_MM)
    ap.add_argument("--json", type=Path, help="결과 JSON 저장 경로")
    args = ap.parse_args()

    if not args.metrics.exists():
        print(f"🔴 평가 결과 없음: {args.metrics}", file=sys.stderr)
        return 1

    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    db = load_db(args.db)
    cond = args.cond or None
    pairs = parse_pairs(metrics, cond)
    if not pairs:
        print(f"🔴 '{cond}' 조건의 매칭 쌍이 없다", file=sys.stderr)
        return 1

    res = analyze(pairs, db, args.tight, args.loose)
    v = res["verdicts"]

    print("=" * 72)
    print(f" 혼동 → 파지 영향 집계   (조건 {cond or '전체'} · 매칭 {res['total_matched']}건)")
    print("=" * 72)
    print(f"  종류 정답률      : {res['label_acc']*100:5.1f}%  "
          f"({res['label_correct']}/{res['total_matched']})")
    print(f"  ⭐파지 가능률    : {res['graspable_rate']*100:5.1f}%  "
          f"({res['graspable']}/{res['total_matched']})")
    print()
    print("  판정 분해")
    print(f"    🟢 무해(라벨 맞음 + 벌림 오차 내) : {v['harmless']:3d}")
    print(f"    🟠 헐거움(벌림이 큼 — 잡히긴 함)  : {v['loose']:3d}")
    print(f"    🔴 치명(벌림 부족 — 안 들어감)    : {v['fatal']:3d}")
    print(f"    ⬜ 판정 불가(DB 미등재)           : {v['unknown']:3d}")
    print()

    if res["fatal_pairs"]:
        print("  🔴 치명 혼동쌍 (여기만 고치면 된다)")
        for f in res["fatal_pairs"]:
            print(f"     GT {f['gt']:30s} → pred {f['pred']:30s} {f['n']}건")
    else:
        print("  ✅ 치명 혼동 없음")
    print()

    print("  임계 민감도 (tight를 흔들어도 결론이 유지되나)")
    for s in sensitivity(pairs, db):
        print(f"     tight {s['tight_mm']:4.1f}mm → 치명 {s['fatal']:3d}건 · "
              f"파지 가능 {s['graspable_rate']*100:5.1f}%")
    print()

    gap = res["graspable_rate"] - res["label_acc"]
    print("  ⭐ 해석")
    print(f"     종류 정답률과 파지 가능률의 차이 = {gap*100:+.1f}%p")
    if gap > 0.15:
        print("     → **'종류를 틀린다'가 곧 '못 집는다'가 아니다.**")
        print("        혼동 대부분이 벌림이 비슷한 쌍이라 파지에는 무해하다.")
        print("     → 성과 보고는 두 숫자를 함께 낼 것(정확도 / 파지 가능률).")
    else:
        print("     → 혼동이 실제로 파지를 막고 있다. 재학습·데이터 보강이 필요하다.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(res)
        payload["sensitivity"] = sensitivity(pairs, db)
        payload["cond"] = cond
        payload["source_metrics"] = str(args.metrics)
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  📄 저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
