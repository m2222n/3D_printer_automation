"""
Blaze ↔ ACE2 Extrinsic 로더 (RGB-D 정합 소비자 측)
====================================================

`calibrate_blaze_ace2_extrinsic.py`가 **쓴** json을 **읽는** 쪽.

⚠️ 7/28 신설 배경: 쓰는 코드만 있고 읽는 코드가 리포 전체에 0건이었음.
   정렬에 성공해 json을 만들어도 아무도 안 읽어서 단계 ②(좌표 출력)로
   넘어갈 수가 없었다. intrinsic은 로더가 있는데(`load_ace2_intrinsics` 등)
   extrinsic만 대칭이 깨져 있던 것.

⭐ 단위 규약 (여기서 못 박음 — 섞이면 1000배 오차)
   - extrinsic json의 translation = **m** (캘리브 스크립트가 square_m 단위로 풀어서)
   - Blaze depth 이미지 = **mm** (uint16)
   - 한솔 6요소 출력 z = **mm**
   → 로더는 `T_m`(원본)과 `T_mm`(translation만 ×1000) 둘 다 제공한다.
     depth를 mm로 다루는 파이프라인은 반드시 `T_mm`을 쓸 것.

사용:
    from bin_picking.src.acquisition.extrinsic_io import load_extrinsic

    ext = load_extrinsic()              # config/blaze_ace2_extrinsic.json
    T = ext.T_mm                        # ACE2 좌표계 점 → Blaze 좌표계 (mm)
    p_blaze = T @ [x, y, z, 1]
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXTRINSIC = PROJECT_ROOT / "bin_picking" / "config" / "blaze_ace2_extrinsic.json"

# SE(3) 유효성 허용 오차. json은 float64 왕복이 무손실이라 넉넉한 값.
_ORTHO_TOL = 1e-6
_DET_TOL = 1e-6

# spread_mm 경고 임계 — 캘리브 스크립트의 "✅ 안정 <5mm" 기준과 맞춤.
SPREAD_WARN_MM = 5.0


class ExtrinsicError(RuntimeError):
    """extrinsic json이 없거나 내용이 SE(3)로서 유효하지 않을 때."""


@dataclass(frozen=True)
class Extrinsic:
    """Blaze ↔ ACE2 상대 변환.

    T_ace2_to_blaze = ACE2 카메라 좌표계의 점을 Blaze 좌표계로 보내는 4×4.
    (캘리브 스크립트의 `Tb @ inv(Ta)` — 이름과 실제 의미가 일치함을 수치 검증 완료)
    """

    T_m: np.ndarray               # 원본 (translation 단위 m)
    baseline_mm: float            # 두 카메라 광학중심 거리
    spread_mm: float              # 프레임 간 translation 산포(캘리브 품질 지표)
    n_frames: int                 # 채택 프레임 수
    source: Path                  # 읽어온 파일 경로

    @property
    def T_mm(self) -> np.ndarray:
        """translation만 mm로 바꾼 4×4. depth(mm) 파이프라인은 이걸 쓸 것."""
        T = self.T_m.copy()
        T[:3, 3] *= 1000.0
        return T

    @property
    def R(self) -> np.ndarray:
        """회전 3×3 (단위 무관)."""
        return self.T_m[:3, :3].copy()

    def inverse_mm(self) -> np.ndarray:
        """Blaze → ACE2 (mm). SE(3) 역변환은 전치로 정확히 구함.

        np.linalg.inv 대신 R^T 사용 — 수치 오차 없이 정확하고,
        되돌렸을 때 원본과 비트 수준으로 가까움.
        """
        T = self.T_mm
        R, t = T[:3, :3], T[:3, 3]
        out = np.eye(4)
        out[:3, :3] = R.T
        out[:3, 3] = -R.T @ t
        return out

    def quality_warnings(self) -> list[str]:
        """캘리브 품질 경고. 로딩은 되지만 결과를 의심해야 하는 경우."""
        warns = []
        if self.spread_mm > SPREAD_WARN_MM:
            warns.append(
                f"⚠️ 프레임 간 산포 {self.spread_mm:.2f}mm > {SPREAD_WARN_MM}mm — "
                f"정합 오차가 큼. 보드를 더 다양한 각도로 재채택 권장."
            )
        if self.n_frames < 5:
            warns.append(
                f"⚠️ 채택 프레임 {self.n_frames}개(권장 5~8) — 평균이 불안정할 수 있음."
            )
        return warns


def _validate_se3(T: np.ndarray, path: Path) -> None:
    """4×4가 진짜 강체변환인지 검사.

    손으로 편집했거나 다른 규약(예: mm로 저장)으로 만든 파일이 조용히
    통과하면 좌표가 통째로 틀어지므로, 읽는 시점에 막는다.
    """
    if T.shape != (4, 4):
        raise ExtrinsicError(f"{path}: T_ace2_to_blaze가 4×4가 아님 (shape={T.shape})")
    if not np.all(np.isfinite(T)):
        raise ExtrinsicError(f"{path}: T에 NaN/Inf 포함")

    R = T[:3, :3]
    ortho_err = float(np.abs(R @ R.T - np.eye(3)).max())
    det = float(np.linalg.det(R))

    if ortho_err > _ORTHO_TOL:
        raise ExtrinsicError(
            f"{path}: 회전부가 직교하지 않음 (R·Rᵀ−I 최대오차 {ortho_err:.2e}). "
            f"파일이 손상됐거나 손으로 편집된 것으로 보임 → 재캘리브 필요."
        )
    if abs(det - 1.0) > _DET_TOL:
        # det ≈ -1이면 반사행렬 = 좌우가 뒤집힌 좌표가 나옴.
        kind = "반사행렬(det≈-1)" if det < 0 else f"스케일 포함(det={det:.6f})"
        raise ExtrinsicError(
            f"{path}: 회전부 det={det:.6f} ≠ 1 — {kind}. 정상 회전이 아님 → 재캘리브 필요."
        )

    last = T[3]
    if not np.allclose(last, [0, 0, 0, 1], atol=1e-9):
        raise ExtrinsicError(f"{path}: 마지막 행이 [0,0,0,1]이 아님 ({last})")


def load_extrinsic(path: Optional[Path] = None, *, strict: bool = True) -> Extrinsic:
    """extrinsic json을 읽어 검증된 `Extrinsic`으로 반환.

    Args:
        path: json 경로. None이면 config/blaze_ace2_extrinsic.json
        strict: True면 품질 경고(산포 큼 등)도 예외로 승격.
                기본 False 동작은 경고만 반환하고 로딩은 성공.

    Raises:
        ExtrinsicError: 파일 없음 / 키 없음 / SE(3) 아님 (+ strict일 때 품질 미달)
    """
    p = Path(path) if path is not None else DEFAULT_EXTRINSIC

    if not p.exists():
        raise ExtrinsicError(
            f"extrinsic 없음: {p}\n"
            f"  → 먼저 B단계 정렬을 완료할 것:\n"
            f"     python bin_picking/tests/calibrate_blaze_ace2_extrinsic.py \\\n"
            f"       --square-mm 25 --blaze-ip 192.168.30.10 \\\n"
            f"       --blaze-exposure 400 --min-corners 4\n"
            f"  ⚠️ 이 json은 git에 없음(캘리브 결과는 로컬 상주) — Mac에서 만든 뒤 옮길 것."
        )

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ExtrinsicError(f"{p}: json 파싱 실패 — {e}") from e

    if "T_ace2_to_blaze" not in d:
        raise ExtrinsicError(
            f"{p}: 'T_ace2_to_blaze' 키 없음 (있는 키: {sorted(d)}). "
            f"캘리브 스크립트가 만든 파일이 맞는지 확인."
        )

    T = np.array(d["T_ace2_to_blaze"], dtype=np.float64)
    _validate_se3(T, p)

    # baseline은 저장값을 믿지 않고 T에서 재계산 — 둘이 어긋나면 파일이 수상하다.
    baseline_mm = float(np.linalg.norm(T[:3, 3]) * 1000.0)
    stored = d.get("baseline_mm")
    if stored is not None and abs(float(stored) - baseline_mm) > 0.1:
        raise ExtrinsicError(
            f"{p}: baseline 불일치 — 저장값 {float(stored):.2f}mm vs "
            f"T에서 계산 {baseline_mm:.2f}mm. 파일이 부분 수정된 것으로 보임."
        )

    ext = Extrinsic(
        T_m=T,
        baseline_mm=baseline_mm,
        spread_mm=float(d.get("spread_mm", float("nan"))),
        n_frames=int(d.get("n_frames", 0)),
        source=p,
    )

    if strict:
        warns = ext.quality_warnings()
        if warns:
            raise ExtrinsicError(f"{p}: 품질 미달(strict)\n  " + "\n  ".join(warns))

    return ext


def describe(ext: Extrinsic) -> str:
    """사람이 읽는 요약 — 로딩 직후 로그에 찍어 눈으로 확인하는 용도."""
    t = ext.T_m[:3, 3]
    lines = [
        f"Extrinsic 로드: {ext.source}",
        f"  T_ace2_to_blaze translation: "
        f"[{t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f}] m",
        f"  baseline: {ext.baseline_mm:.1f} mm  (두 카메라 광학중심 거리)",
        f"  캘리브 품질: 산포 {ext.spread_mm:.2f} mm / 채택 {ext.n_frames} 프레임",
    ]
    lines += [f"  {w}" for w in ext.quality_warnings()]
    return "\n".join(lines)


if __name__ == "__main__":
    # 실사용 전 눈으로 확인: python -m bin_picking.src.acquisition.extrinsic_io
    import sys

    try:
        e = load_extrinsic(strict=False)
    except ExtrinsicError as err:
        print(f"[ERROR] {err}")
        sys.exit(1)
    print(describe(e))
