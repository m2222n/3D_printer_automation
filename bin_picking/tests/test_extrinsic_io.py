"""
extrinsic_io 로더 테스트 — 카메라 없이 검증
=============================================

핵심 검증: **캘리브 스크립트가 쓴 것을 로더가 그대로 되읽는가**(왕복).
쓰는 쪽 함수(`to_T`)를 직접 import해서 형식이 갈라지는 걸 막는다.

    python bin_picking/tests/test_extrinsic_io.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from bin_picking.src.acquisition.extrinsic_io import (  # noqa: E402
    Extrinsic,
    ExtrinsicError,
    load_extrinsic,
)

# 쓰는 쪽 함수를 그대로 가져와 형식 갈라짐 방지
sys.path.insert(0, str(PROJECT_ROOT / "bin_picking" / "tests"))
from calibrate_blaze_ace2_extrinsic import to_T  # noqa: E402


def _pose(rvec, tvec):
    return to_T(np.array(rvec, np.float64), np.array(tvec, np.float64))


def _write_calib_json(path: Path, T: np.ndarray, *, spread_mm=1.2, n_frames=6,
                      baseline_mm=None):
    """캘리브 스크립트 main()이 저장하는 것과 동일한 스키마로 기록."""
    t = T[:3, 3]
    result = {
        "T_ace2_to_blaze": T.tolist(),
        "translation_m": t.tolist(),
        "baseline_mm": float(np.linalg.norm(t) * 1000) if baseline_mm is None
        else baseline_mm,
        "spread_mm": spread_mm,
        "n_frames": n_frames,
        "board": {"squares_x": 7, "squares_y": 5, "square_mm": 25.0},
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))


def _make_ground_truth():
    """캘리브가 실제로 하는 계산을 재현: Tb @ inv(Ta)."""
    Tb = _pose([0.10, 0.05, 0.02], [0.010, 0.020, 0.500])   # board→blaze
    Ta = _pose([0.12, 0.04, 0.03], [0.030, 0.010, 0.480])   # board→ace2
    return Tb @ np.linalg.inv(Ta), Tb, Ta


# ============================================================
def test_roundtrip_write_then_read(tmp: Path):
    """쓴 값 == 읽은 값 (무손실)."""
    T_true, _, _ = _make_ground_truth()
    p = tmp / "blaze_ace2_extrinsic.json"
    _write_calib_json(p, T_true)

    ext = load_extrinsic(p)
    assert np.array_equal(ext.T_m, T_true), "왕복 손실 발생"
    print("  ✅ 왕복 무손실 (비트 단위 동일)")


def test_semantics_ace2_to_blaze(tmp: Path):
    """T가 정말 ACE2 좌표의 점을 Blaze 좌표로 보내는가 (이름값 검증)."""
    T_true, Tb, Ta = _make_ground_truth()
    p = tmp / "e.json"
    _write_calib_json(p, T_true)
    ext = load_extrinsic(p)

    p_board = np.array([0.05, 0.03, 0.0, 1.0])
    p_ace2 = Ta @ p_board
    p_blaze_true = Tb @ p_board
    p_blaze_got = ext.T_m @ p_ace2

    err = float(np.abs(p_blaze_got - p_blaze_true).max())
    assert err < 1e-12, f"의미 불일치 (오차 {err:.2e})"
    print(f"  ✅ ACE2→Blaze 매핑 정확 (오차 {err:.1e} m)")


def test_unit_mm_conversion(tmp: Path):
    """T_mm은 translation만 ×1000, 회전은 불변."""
    T_true, _, _ = _make_ground_truth()
    p = tmp / "e.json"
    _write_calib_json(p, T_true)
    ext = load_extrinsic(p)

    assert np.allclose(ext.T_mm[:3, :3], ext.T_m[:3, :3]), "회전이 변형됨"
    assert np.allclose(ext.T_mm[:3, 3], ext.T_m[:3, 3] * 1000.0), "translation 변환 오류"
    assert abs(np.linalg.norm(ext.T_mm[:3, 3]) - ext.baseline_mm) < 1e-9
    print(f"  ✅ mm 변환 정확 (baseline {ext.baseline_mm:.1f} mm)")


def test_inverse_roundtrip(tmp: Path):
    """정변환 → 역변환 하면 제자리."""
    T_true, _, _ = _make_ground_truth()
    p = tmp / "e.json"
    _write_calib_json(p, T_true)
    ext = load_extrinsic(p)

    pt = np.array([12.0, -34.0, 800.0, 1.0])       # mm, ACE2 좌표
    back = ext.inverse_mm() @ (ext.T_mm @ pt)
    err = float(np.abs(back - pt).max())
    assert err < 1e-9, f"역변환 왕복 오차 {err:.2e} mm"
    print(f"  ✅ 역변환 왕복 오차 {err:.1e} mm")


def test_missing_file_message():
    """파일 없을 때: 예외 + 다음 행동이 적힌 메시지."""
    try:
        load_extrinsic(Path("/nonexistent/nope.json"))
    except ExtrinsicError as e:
        msg = str(e)
        assert "calibrate_blaze_ace2_extrinsic.py" in msg, "다음 행동 안내 없음"
        print("  ✅ 파일 없음 → 재캘리브 명령 안내됨")
        return
    raise AssertionError("예외가 안 났음")


def test_rejects_reflection(tmp: Path):
    """det=-1 (반사행렬) 거부 — 좌우 뒤집힌 좌표를 조용히 내보내면 안 됨."""
    T_bad = np.eye(4)
    T_bad[:3, :3] = np.diag([1.0, 1.0, -1.0])       # det = -1
    T_bad[:3, 3] = [0.01, 0.02, 0.05]
    p = tmp / "bad.json"
    _write_calib_json(p, T_bad)

    try:
        load_extrinsic(p)
    except ExtrinsicError as e:
        assert "det" in str(e)
        print("  ✅ 반사행렬 거부")
        return
    raise AssertionError("반사행렬이 통과됨")


def test_rejects_non_orthogonal(tmp: Path):
    """손편집 등으로 회전부가 깨진 경우 거부."""
    T_true, _, _ = _make_ground_truth()
    T_bad = T_true.copy()
    T_bad[0, 0] += 0.05                              # 직교성 파괴
    p = tmp / "bad2.json"
    _write_calib_json(p, T_bad)

    try:
        load_extrinsic(p)
    except ExtrinsicError as e:
        assert "직교" in str(e)
        print("  ✅ 비직교 회전 거부")
        return
    raise AssertionError("깨진 회전이 통과됨")


def test_rejects_mm_saved_as_m(tmp: Path):
    """⭐ 실수 시나리오: translation을 mm로 저장한 파일.

    회전은 멀쩡하니 SE(3) 검사는 통과 → baseline 교차검증이 잡아야 한다.
    (여기서 못 잡으면 1000배 어긋난 좌표가 로봇까지 감)
    """
    T_true, _, _ = _make_ground_truth()
    T_mm = T_true.copy()
    T_mm[:3, 3] *= 1000.0                            # m 대신 mm를 넣어버림
    p = tmp / "unit_bug.json"
    # baseline_mm은 올바른 m 기준으로 기록 → 불일치 발생
    _write_calib_json(p, T_mm, baseline_mm=float(np.linalg.norm(T_true[:3, 3]) * 1000))

    try:
        load_extrinsic(p)
    except ExtrinsicError as e:
        assert "baseline" in str(e)
        print("  ✅ 단위 혼동(mm를 m 자리에) 검출")
        return
    raise AssertionError("단위 버그가 통과됨")


def test_quality_warning_and_strict(tmp: Path):
    """산포 큰 캘리브: 기본은 경고만, strict면 예외."""
    T_true, _, _ = _make_ground_truth()
    p = tmp / "loose.json"
    _write_calib_json(p, T_true, spread_mm=12.0, n_frames=3)

    ext = load_extrinsic(p, strict=False)
    warns = ext.quality_warnings()
    assert len(warns) == 2, f"경고 2건 기대, 실제 {len(warns)}"
    print(f"  ✅ 품질 경고 {len(warns)}건 (산포 12mm, 3프레임)")

    try:
        load_extrinsic(p, strict=True)
    except ExtrinsicError:
        print("  ✅ strict=True 에서 예외 승격")
        return
    raise AssertionError("strict가 통과시킴")


def test_missing_key(tmp: Path):
    p = tmp / "nokey.json"
    p.write_text(json.dumps({"baseline_mm": 50.0}))
    try:
        load_extrinsic(p)
    except ExtrinsicError as e:
        assert "T_ace2_to_blaze" in str(e)
        print("  ✅ 키 누락 거부")
        return
    raise AssertionError("키 없는 파일이 통과됨")


def main() -> int:
    tests = [
        ("왕복 무손실", test_roundtrip_write_then_read),
        ("ACE2→Blaze 의미", test_semantics_ace2_to_blaze),
        ("mm 단위 변환", test_unit_mm_conversion),
        ("역변환 왕복", test_inverse_roundtrip),
        ("파일 없음 안내", None),
        ("반사행렬 거부", test_rejects_reflection),
        ("비직교 거부", test_rejects_non_orthogonal),
        ("단위 혼동 검출", test_rejects_mm_saved_as_m),
        ("품질 경고/strict", test_quality_warning_and_strict),
        ("키 누락 거부", test_missing_key),
    ]
    print("=" * 60)
    print("extrinsic_io 로더 테스트 (카메라 불필요)")
    print("=" * 60)

    failed = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in tests:
            print(f"\n[{name}]")
            try:
                if fn is None:
                    test_missing_file_message()
                else:
                    fn(tmp)
            except AssertionError as e:
                print(f"  ❌ FAIL: {e}")
                failed += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ❌ ERROR: {type(e).__name__}: {e}")
                failed += 1

    print("\n" + "=" * 60)
    if failed:
        print(f"❌ {failed}/{len(tests)} 실패")
        return 1
    print(f"✅ 전부 통과 ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
