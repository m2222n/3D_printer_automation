#!/usr/bin/env python3
"""E2E 결과 대조 — 두 서버(6000 ↔ IPC/Thor)가 **같은 답**을 내는지 검사.

🚨🚨 왜 이 도구가 필요한가 (8/14 실측)
   `--real_uint16_max_depth_m`를 빼면 검출이 **9건 → 10건으로 늘어나는데**
   좌우(`_l`/`_r`)가 뒤바뀌고 부품 종류가 달라진다. **에러도 경고도 없다.**
   ⇒ ⭐⭐ **"개수가 같다"는 합격 판정이 아니다.** 이름·score·좌표를 대조해야 한다.

🚨 8/21 사고도 같은 계열
   A100 평가기가 7/6자로 낡아 c2 기준선이 0.0985 → 0.1281로 바뀌었다.
   md5(데이터·라벨 동일) → 플래그(동일) → **코드에서 갈렸다.**
   ⇒ 📌 **"같은 조건"에는 코드 버전도 들어간다.** 그래서 환경 지문까지 비교한다.

무엇을 비교하나 — 엄격한 순서로
   ① 장면 수 · 검출 개수
   ② ⭐ **부품 이름 집합** (좌우 뒤바뀜을 여기서 잡는다)
   ③ ⭐ **label별 score** (기본 허용 1e-4 — 소수점까지 일치해야 한다)
   ④ ⭐ **좌표 x,y,z** (기본 허용 0.5mm)
   ⑤ 게이트 판정 (`verdict`·`trusted`·`valid_ratio_pct`)
   ⑥ 환경 지문 (torch/numpy 버전 · ckpt md5) — 있으면 비교, 없으면 경고

사용법:
    # 6000에서 기준선 만들기
    python run_binpick_e2e.py --depth-dir <npy> --glob "shot_00[1-5]_c1.npy" \
        --out-dir ref5 --python /data/jtm/depth_venv/bin/python

    # IPC에서 같은 명령 → out-dir ipc5
    # 대조
    python compare_e2e_results.py --ref ref5 --test ipc5

    python compare_e2e_results.py --ref ref5 --test ipc5 --score-tol 1e-3 --pos-tol 1.0
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

# 기본 허용오차 — 왜 이 값인가
#   score: 같은 가중치·같은 입력이면 **비트 단위로 같아야** 한다. 1e-4는 float32 출력
#          포맷팅 차이만 흡수하는 값이고, 이보다 크면 연산 경로가 다른 것이다.
#   pos  : 좌표는 픽셀→mm 변환을 거치므로 반올림 차이가 생길 수 있다. 0.5mm는
#          1px(≈1.45mm @450mm)의 1/3 — 이보다 크면 crop/intrinsic이 다르다.
DEF_SCORE_TOL = 1e-4
DEF_POS_TOL = 0.5


def load_six(dirpath):
    """out-dir 안의 six/*.six.json 을 {scene_stem: data} 로."""
    pat = os.path.join(dirpath, "six", "*.six.json")
    files = sorted(glob.glob(pat))
    if not files:
        # out-dir 를 직접 six 디렉토리로 준 경우도 받아준다
        files = sorted(glob.glob(os.path.join(dirpath, "*.six.json")))
    if not files:
        raise SystemExit(
            f"🔴 six JSON이 없다: {pat}\n"
            f"   ⭐ '차이 없음'이 아니라 '결과가 없다'는 뜻이다."
        )
    out = {}
    for f in files:
        stem = os.path.basename(f).replace(".six.json", "")
        out[stem] = json.loads(open(f, encoding="utf-8").read())
    return out


def det_key(d):
    """검출 하나를 비교 가능한 형태로. label + 위치로 대응을 잡는다."""
    return (d.get("label"), round(float(d.get("x", 0))), round(float(d.get("y", 0))))


def compare_scene(ref, test, score_tol, pos_tol):
    """장면 하나 비교 → 문제 메시지 리스트."""
    msgs = []

    rd, td = ref.get("detections", []), test.get("detections", [])
    if len(rd) != len(td):
        msgs.append(f"검출 개수 {len(td)} ≠ 기준 {len(rd)}")

    # ② 이름 집합 — 좌우 뒤바뀜을 여기서 잡는다
    rn, tn = Counter(d.get("label") for d in rd), Counter(d.get("label") for d in td)
    if rn != tn:
        only_ref = rn - tn
        only_test = tn - rn
        if only_ref:
            msgs.append(f"🚨기준에만 있는 부품 {dict(only_ref)}")
        if only_test:
            msgs.append(f"🚨테스트에만 있는 부품 {dict(only_test)}")
        # 좌우 뒤바뀜 특별 경고 (8/14 사고 형태)
        for lab in list(only_ref) + list(only_test):
            if lab and (lab.endswith("_l") or lab.endswith("_r")):
                msgs.append(
                    f"🚨🚨 '{lab}' — **좌우 접미사 부품이 어긋났다**. "
                    "8/14에 `--real_uint16_max_depth_m` 누락으로 정확히 이 증상이 났다"
                )
                break

    # ③④ label+위치로 대응 잡고 score·좌표 비교
    rmap = {det_key(d): d for d in rd}
    tmap = {det_key(d): d for d in td}
    for k in sorted(set(rmap) & set(tmap), key=lambda x: (str(x[0]), x[1], x[2])):
        a, b = rmap[k], tmap[k]
        for fld, tol, unit in (("confidence", score_tol, ""), ("cad_score", score_tol, "")):
            va, vb = a.get(fld), b.get(fld)
            if va is None or vb is None:
                continue
            if abs(float(va) - float(vb)) > tol:
                msgs.append(f"'{k[0]}' {fld} {vb} ≠ {va} (차 {abs(float(va)-float(vb)):.2e})")
        for fld in ("x", "y", "z"):
            va, vb = a.get(fld), b.get(fld)
            if va is None or vb is None:
                continue
            if abs(float(va) - float(vb)) > pos_tol:
                msgs.append(f"'{k[0]}' {fld} {vb} ≠ {va} (차 {abs(float(va)-float(vb)):.2f}mm)")

    # ⑤ 게이트
    rg, tg = ref.get("gate_scene") or {}, test.get("gate_scene") or {}
    for fld in ("verdict", "trusted"):
        if rg.get(fld) != tg.get(fld):
            msgs.append(f"게이트 {fld}: {tg.get(fld)} ≠ {rg.get(fld)}")
    ra, ta = rg.get("valid_ratio_pct"), tg.get("valid_ratio_pct")
    if ra is not None and ta is not None and abs(float(ra) - float(ta)) > 0.01:
        msgs.append(f"게이트 유효율 {ta}% ≠ {ra}%")
    # 🚨 gate_dropped 는 제외된 검출 **객체 리스트**다(개수가 아니다).
    #    그대로 찍으면 한 줄이 수백 자가 되어 읽을 수 없다 ⇒ 개수 + 부품 이름만 낸다.
    def _dropped_summary(v):
        if not v:
            return 0, []
        if isinstance(v, int):
            return v, []
        names = sorted(Counter(
            (d.get("gate", {}) or {}).get("excluded_part") or d.get("label") or "?"
            for d in v if isinstance(d, dict)
        ).items())
        return len(v), names

    rn_drop, rnames = _dropped_summary(ref.get("gate_dropped"))
    tn_drop, tnames = _dropped_summary(test.get("gate_dropped"))
    if rn_drop != tn_drop or rnames != tnames:
        def _fmt(n, names):
            return f"{n}건" + (f" {dict(names)}" if names else "")
        msgs.append(f"게이트 제외 {_fmt(tn_drop, tnames)} ≠ 기준 {_fmt(rn_drop, rnames)}")

    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="기준선 out-dir (6000에서 만든 것)")
    ap.add_argument("--test", required=True, help="검사 대상 out-dir (IPC/Thor)")
    ap.add_argument("--score-tol", type=float, default=DEF_SCORE_TOL)
    ap.add_argument("--pos-tol", type=float, default=DEF_POS_TOL)
    args = ap.parse_args()

    ref = load_six(args.ref)
    test = load_six(args.test)

    print(f"기준선 {len(ref)}장 ({args.ref})")
    print(f"대상   {len(test)}장 ({args.test})")
    print(f"허용   score {args.score_tol:g} · 좌표 {args.pos_tol}mm\n")

    missing = sorted(set(ref) - set(test))
    extra = sorted(set(test) - set(ref))
    if missing:
        print(f"  🔴 대상에 없는 장면 {len(missing)}개: {', '.join(missing[:5])}")
    if extra:
        print(f"  🟡 기준선에 없는 장면 {len(extra)}개: {', '.join(extra[:5])}")

    bad_scenes = 0
    total_msgs = 0
    for stem in sorted(set(ref) & set(test)):
        msgs = compare_scene(ref[stem], test[stem], args.score_tol, args.pos_tol)
        if msgs:
            bad_scenes += 1
            total_msgs += len(msgs)
            print(f"  🔴 {stem}")
            for m in msgs:
                print(f"       {m}")

    # ⑥ 환경 지문 — 8/21 "같은 조건에는 코드 버전이 들어간다"
    print()
    fp_ref = _fingerprint(args.ref)
    fp_test = _fingerprint(args.test)
    if fp_ref or fp_test:
        for k in sorted(set(fp_ref) | set(fp_test)):
            a, b = fp_ref.get(k), fp_test.get(k)
            mark = "🟢" if a == b else "🔴"
            print(f"  {mark} {k}: 기준 {a} / 대상 {b}")
    else:
        print("  ⚠️ 환경 지문(env.json)이 양쪽에 없다 — torch/numpy 버전·ckpt md5를"
              " 비교할 수 없다. `--emit-env` 로 남기는 것을 권한다")

    n = len(set(ref) & set(test))
    print(f"\n{'='*62}")
    print(f"  대조한 장면 : {n}")
    print(f"  불일치 장면 : {bad_scenes}  (항목 {total_msgs}건)")
    bad = bad_scenes + len(missing)
    if bad:
        print(f"  🔴 이식 검증 실패 — **이 상태로 로봇에 연결하지 말 것**")
        print(f"     ⭐ 먼저 볼 것 = 추론 플래그 6개 · ckpt md5 · torch 버전")
    else:
        print(f"  ✅ 소수점까지 일치 — 이식 검증 통과")
        print(f"     ⭐ 8/14 기준선(6000 ↔ IPC 9건 일치)과 같은 판정 방식")
    print(f"{'='*62}")
    return 1 if bad else 0


def _fingerprint(dirpath):
    """out-dir 안 env.json 이 있으면 읽는다(없으면 빈 dict)."""
    for p in (os.path.join(dirpath, "env.json"),
              os.path.join(dirpath, "..", "env.json")):
        if os.path.exists(p):
            try:
                return json.loads(open(p, encoding="utf-8").read())
            except Exception:
                pass
    return {}


if __name__ == "__main__":
    sys.exit(main())
