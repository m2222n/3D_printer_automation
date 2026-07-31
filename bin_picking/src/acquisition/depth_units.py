"""Blaze depth 단위 변환 — **한 곳에서만** 한다.

🚨 왜 이 파일이 생겼나 (2026-07-31)
   같은 단위 버그를 **나흘에 네 번** 밟았다. 전부 "조용히 그럴싸한 값"이 나오는 종류라
   에러 없이 틀린 결과만 남았다:

     7/29  6요소 z가 6~7배 과대(3136mm)          — raw를 mm로 오인
     7/30  촬영 게이지가 20장 전부 NOT OK        — 같은 오인 (표시 2788~3212mm)
     7/30  detect 인자 누락으로 검출 9건→2건     — max_depth_m 기본값 미전달
     7/31  오버레이 z가 902mm(실제 ~500mm)       — 같은 오인, 정합 판정을 무효화

   원인은 매번 "변환을 그 파일에서 다시 짰기" 때문이다. 파일마다 고쳐도 다음 파일에서
   또 밟는다. → **변환식을 여기 하나로 모으고, 새 코드는 반드시 이 함수를 쓴다.**

⭐ 변환식 (근거: `depth_preprocess.py:54`, `eval_real_depth_vq_detector.py:135`)

       depth_m = raw_uint16 × (max_depth_m / 65535)      , 기본 max_depth_m = 10.0
       depth_mm = depth_m × 1000

   즉 **저장된 npy의 uint16은 mm가 아니다.** raw 3212 → 490mm.

⚠️ 라이브 스트림이 이미 mm일 가능성은 현장 미확인이라, 판정 헬퍼를 함께 둔다.
   저장 원본은 어느 경로든 raw 그대로이므로 **데이터 자체는 안전**하다.
"""
from __future__ import annotations

import numpy as np

# Blaze 실측 npy의 기본 스케일. eval 기본값(`--real_uint16_max_depth_m`)과 같아야 한다.
DEFAULT_MAX_DEPTH_M = 10.0

# 빈피킹 작업 대역(mm). 학습셋이 이 범위에서 촬영됐다(`--depth_keep_range 0.40,0.60`).
WORK_BAND_MM = (400.0, 600.0)


def raw_to_mm(raw: np.ndarray, max_depth_m: float = DEFAULT_MAX_DEPTH_M) -> np.ndarray:
    """Blaze raw uint16 → mm (float32). raw==0은 무효라 0으로 남는다."""
    if max_depth_m <= 0:
        raise ValueError(f"max_depth_m는 양수여야 함 (받은 값 {max_depth_m})")
    return raw.astype(np.float32) * (float(max_depth_m) / 65535.0) * 1000.0


def mm_to_raw(mm: float, max_depth_m: float = DEFAULT_MAX_DEPTH_M) -> int:
    """테스트용 역변환. 500mm → raw 3277."""
    return int(round(mm / 1000.0 / float(max_depth_m) * 65535.0))


def implausible_as_mm(depth: np.ndarray) -> bool:
    """이 배열을 **mm로 해석하면 물리적으로 말이 안 되는가**(=raw 의심).

    ⚠️ 자동 추측은 신뢰하지 말 것. 처음엔 "중앙값 5000 초과면 raw"로 판정했는데,
       실측 npy(raw 중앙 2899 = 실제 442mm)가 임계 아래라 **"이미 mm"로 오판**했다.
       raw와 mm는 값 범위가 겹쳐 **원리상 완전 판별이 불가능**하다.
       (raw 2899을 mm로 읽으면 2.9m — 실내 거리로 그럴싸하다. 이것이 지난 네 번의
       버그가 전부 "조용히 그럴싸한 값"이었던 이유다.)

    ⭐ 그래서 이 함수는 **판정이 아니라 경고용**이다. dtype이 uint16이면
       Blaze 원본일 가능성이 높다는 사실과 함께 호출자에게 확인을 요구한다.
    """
    v = depth[np.isfinite(depth) & (depth > 0)]
    if v.size == 0:
        return False
    med = float(np.median(v))
    lo, hi = WORK_BAND_MM
    # 작업 대역(400~600mm)에서 한참 벗어나면 단위를 의심할 근거가 된다.
    return not (lo * 0.5 <= med <= hi * 2.0)


def to_mm(
    depth: np.ndarray,
    raw_is_mm: bool = False,
    max_depth_m: float = DEFAULT_MAX_DEPTH_M,
    verbose: bool = True,
) -> tuple[np.ndarray, str]:
    """Blaze depth를 **mm로** 만들어 돌려준다.

    Returns: (mm 배열, 무엇을 했는지 설명 문자열)

    ⭐ 규약 = **uint16이면 raw로 간주하고 변환한다.** 추측하지 않는다.
       Blaze가 내보내는 Coord3D_C16/Mono16이 곧 uint16이고, 저장 npy도 uint16이다.
       실수형(float)이면 이미 변환을 거친 것으로 보고 통과시킨다.
       예외가 필요하면 호출자가 `raw_is_mm=True`로 **명시**한다.

    ⚠️ 이렇게 정한 이유: 값만 보고 raw/mm를 가르려던 첫 시도가 실측에서 곧바로
       오판했다(raw 2899를 "이미 mm"로 판정). 값 범위가 겹치므로 **dtype이라는
       명확한 신호**를 쓰고, 애매하면 경고를 띄워 사람이 정하게 한다.
    """
    if raw_is_mm:
        return depth.astype(np.float32), "raw_is_mm=True(명시) — 변환 없이 mm로 간주"

    if depth.dtype == np.uint8:
        raise ValueError(
            "uint8 배열 — depth가 아니라 밝기 영상일 가능성이 큽니다. "
            "Blaze Range 컴포넌트 전환을 확인하세요."
        )

    if np.issubdtype(depth.dtype, np.integer):
        out = raw_to_mm(depth, max_depth_m)
        v = out[out > 0]
        med = float(np.median(v)) if v.size else float("nan")
        msg = (f"{depth.dtype} → raw로 간주해 mm 변환"
               f"(×{max_depth_m}/65535×1000). 중앙값 {med:.0f}mm")
        if verbose:
            print(f"[depth_units] {msg}")
            if implausible_as_mm(out):
                print(f"[depth_units] ⚠️ 변환 후 중앙값 {med:.0f}mm가 작업 대역"
                      f"({WORK_BAND_MM[0]:.0f}~{WORK_BAND_MM[1]:.0f}mm)에서 멀다. "
                      f"카메라 거리나 --raw-is-mm 여부를 확인할 것.")
        return out, msg

    out = depth.astype(np.float32)
    msg = "실수형 — 이미 mm로 변환된 것으로 간주(변환 없음)"
    if verbose and implausible_as_mm(out):
        v = out[out > 0]
        med = float(np.median(v)) if v.size else float("nan")
        print(f"[depth_units] ⚠️ {msg} 그런데 중앙값 {med:.0f}mm가 작업 대역 밖이다. "
              f"단위를 다시 확인할 것.")
    return out, msg
