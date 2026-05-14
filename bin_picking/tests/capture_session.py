"""
캡처 세션 wrapper — yaw sweep 자동화 + 메타데이터 보장
=========================================================

5/15 본 캡처 시 SOP § 2.2 의 bash for-loop 를 Python 으로 대체.

설계 목표:
- yaw 사람 입력 자동 갱신 (bash에서 sed 로 meta.json 수정하던 것 제거)
- 진행 카운터 + 예상 잔여 시간
- 중단/재개 (--resume): 이미 캡처된 frame 건너뛰기
- capture_session.json 으로 세션 메타 (부품 / 자세 / 조명 / 배경 / yaw 리스트 / 시작·종료 시각) 저장
- 첫 캡처 시 라이브 뷰어로 valid % 70%+ 사전 확인 안내

사용 예 (5/15 P5 main_body 자세 A):
    # 환경 (Mac)
    export BASLER_BLAZE_IP=192.168.20.10
    source .venv/binpick/bin/activate

    # 캡처 세션 시작 (yaw 0~345 / 15° 간격, 24장)
    python bin_picking/tests/capture_session.py \\
        --part main_body --pose A --light normal --bg white \\
        --yaw-step 15

    # SOP v1.1 차원 축소 (12장, 30° 간격):
    python bin_picking/tests/capture_session.py \\
        --part main_body --pose A --light normal --bg white \\
        --yaw-step 30

    # 중단된 세션 재개:
    python bin_picking/tests/capture_session.py \\
        --resume bin_picking/models/captures/20260515_main_body_poseA_normal_white

대화 흐름 (각 yaw):
    [3/24] 회전대를 yaw=30° 로 맞추세요
    → 부품 흔들림 없는지 확인 후 Enter (또는 's' 스킵)
    → 캡처 (--live --save)
    → meta.json 에 part_id/pose/yaw/light/bg 자동 추가

종료 후:
    - 세션 디렉토리에 capture_session.json (전체 메타)
    - 다음 단계 안내: auto_label.py 명령어 출력

⚠️ 사용 전 라이브 뷰어로 부품 위치 + valid % 70%+ 확인 필수 (SOP § 1.3):
    python bin_picking/tests/live_viewer_basler.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE_ROOT = PROJECT_ROOT / "bin_picking" / "models" / "captures"


# ============================================================
# 세션 디렉토리 + 메타
# ============================================================
def session_dir_name(part: str, pose: str, light: str, bg: str, date_str: Optional[str] = None) -> str:
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    return f"{date_str}_{part}_pose{pose}_{light}_{bg}"


def init_session(
    capture_root: Path,
    part: str,
    pose: str,
    light: str,
    bg: str,
    yaw_list: list[int],
    intrinsics_version_hint: str = "estimated_v2_20260513",
) -> Path:
    """세션 디렉토리 생성 + capture_session.json 초기화."""
    name = session_dir_name(part, pose, light, bg)
    session_path = capture_root / name
    session_path.mkdir(parents=True, exist_ok=True)

    session_meta = {
        "part_id": part,
        "stable_pose_id": pose,
        "light": light,
        "background": bg,
        "yaw_list_deg": yaw_list,
        "n_frames_planned": len(yaw_list),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": None,
        "intrinsics_version_hint": intrinsics_version_hint,
        "frames_captured": [],
        "frames_skipped": [],
    }
    meta_path = session_path / "capture_session.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps(session_meta, ensure_ascii=False, indent=2))
    return session_path


def load_session(session_path: Path) -> dict:
    """기존 세션 로드 (--resume)."""
    meta_path = session_path / "capture_session.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"capture_session.json 없음: {session_path}")
    return json.loads(meta_path.read_text())


def save_session(session_path: Path, session: dict) -> None:
    meta_path = session_path / "capture_session.json"
    meta_path.write_text(json.dumps(session, ensure_ascii=False, indent=2))


# ============================================================
# 프레임 캡처 + 메타 갱신
# ============================================================
def capture_one_frame(
    session_path: Path,
    frame_name: str,
    no_ace2: bool = True,
) -> tuple[bool, str]:
    """test_basler_live.py --live --save 호출.

    Returns: (success, message)
    """
    frame_dir = session_path / frame_name
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bin_picking" / "tests" / "test_basler_live.py"),
        "--live", "--save",
        "--output", str(frame_dir),
    ]
    if no_ace2:
        cmd.append("--no-ace2")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # 마지막 500자만 (긴 traceback 자르기)
        err = (result.stderr or result.stdout)[-500:]
        return False, f"캡처 실패: {err}"
    return True, "OK"


def append_frame_meta(
    frame_dir: Path,
    part: str,
    pose: str,
    yaw: int,
    light: str,
    bg: str,
    pitch: int = 0,
) -> None:
    """test_basler_live.py 가 만든 meta.json 에 세션 라벨 필드 추가."""
    meta_path = frame_dir / "meta.json"
    if not meta_path.exists():
        # 캡처가 실패해서 meta 없을 수도 있음
        return
    meta = json.loads(meta_path.read_text())
    meta.update({
        "part_id": part,
        "stable_pose_id": pose,
        "yaw_deg": yaw,
        "pitch_deg": pitch,
        "light": light,
        "background": bg,
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


# ============================================================
# 메인 세션 루프
# ============================================================
def run_session(
    session_path: Path,
    session: dict,
    no_ace2: bool = True,
    auto_advance_after_sec: float = 0.0,
) -> int:
    """세션의 모든 yaw 에 대해 캡처. 이미 찍힌 프레임은 건너뜀.

    Returns: 캡처 성공 프레임 수.
    """
    part = session["part_id"]
    pose = session["stable_pose_id"]
    light = session["light"]
    bg = session["background"]
    yaw_list = session["yaw_list_deg"]
    captured = set(session.get("frames_captured", []))

    n_total = len(yaw_list)
    n_done_initial = len(captured)

    print("=" * 70)
    print(f"캡처 세션: {session_path.name}")
    print(f"부품: {part}  자세: {pose}  조명: {light}  배경: {bg}")
    print(f"yaw 리스트: {yaw_list} ({n_total}장)")
    print(f"이미 캡처됨: {n_done_initial}장 (--resume 모드)" if n_done_initial else "신규 세션")
    print("=" * 70)

    if not captured:
        print(
            "\n⚠️ 사전 점검 (SOP v1.1 § 1.2 / § 1.3 / § 4.1):\n"
            "  1. 라이브 뷰어로 valid % > 70% 확인 (`live_viewer_basler.py`)\n"
            "  2. 카메라 흔들림 없음 (회전대 미사용 시 부품 없이 5장 RMS 검증)\n"
            "  3. A4 평면 sanity check 통과 (`check_intrinsics_planar.py`)\n"
            "  4. 회전대 운영 (5/14 추가):\n"
            "     - 회전대 0° = 카메라 방향 기준점 표시 (출발점 일관)\n"
            "     - 검은 배경 시트 깔기 (DBSCAN 회전대 미혼입)\n"
            "     - 회전대 가장자리/아래에서 손으로 돌리기 (시야에 손 안 들어가게)\n"
            "     - 회전 후 1~2초 정지 → 부품 흔들림 가라앉은 후 캡처\n"
        )
        input("준비 완료 시 Enter (취소: Ctrl+C): ")

    t_session_start = time.time()
    n_success = n_done_initial

    for i, yaw in enumerate(yaw_list):
        frame_name = f"frame_{i:04d}_yaw{yaw:03d}"
        frame_dir = session_path / frame_name

        if frame_name in captured:
            print(f"\n[{i + 1}/{n_total}] yaw={yaw}° — 이미 캡처됨, 건너뜀")
            continue

        # 진행 + ETA
        elapsed_per_frame = (time.time() - t_session_start) / max(i - n_done_initial, 1) if i > n_done_initial else 0
        remaining = (n_total - i) * elapsed_per_frame
        eta_str = f"  ETA ~{remaining / 60:.1f}분" if elapsed_per_frame > 0 else ""

        print(f"\n[{i + 1}/{n_total}] yaw={yaw}° (frame {frame_name}){eta_str}")
        print(f"  → 회전대를 {yaw}° 로 맞추고 부품 위치 확인")

        if auto_advance_after_sec > 0:
            print(f"  → {auto_advance_after_sec}초 후 자동 캡처...")
            time.sleep(auto_advance_after_sec)
            user_input = ""
        else:
            user_input = input("  Enter=캡처 / s=스킵 / q=종료: ").strip().lower()

        if user_input == "q":
            print("\n[중단] 사용자 종료 요청")
            break

        if user_input == "s":
            print(f"  → yaw={yaw}° 스킵 (사용자 요청)")
            session["frames_skipped"].append({"frame": frame_name, "yaw": yaw, "reason": "user_skip"})
            save_session(session_path, session)
            continue

        # 캡처
        success, msg = capture_one_frame(session_path, frame_name, no_ace2=no_ace2)
        if not success:
            print(f"  ❌ {msg}")
            session["frames_skipped"].append({"frame": frame_name, "yaw": yaw, "reason": msg})
            save_session(session_path, session)
            retry = input("  재시도? (y/N): ").strip().lower()
            if retry == "y":
                success, msg = capture_one_frame(session_path, frame_name, no_ace2=no_ace2)
                if not success:
                    print(f"  ❌ 재시도 실패: {msg}")
                    continue
            else:
                continue

        # meta.json 라벨 갱신
        append_frame_meta(frame_dir, part, pose, yaw, light, bg)

        session["frames_captured"].append(frame_name)
        save_session(session_path, session)
        n_success += 1
        print(f"  ✅ 캡처 완료 ({n_success}/{n_total})")

    # 세션 종료
    session["completed_at"] = datetime.now().isoformat(timespec="seconds")
    save_session(session_path, session)

    elapsed_total = time.time() - t_session_start
    print("\n" + "=" * 70)
    print(f"세션 완료: {session_path.name}")
    print(f"  성공: {n_success} / {n_total}")
    print(f"  스킵: {len(session['frames_skipped'])}")
    print(f"  소요: {elapsed_total / 60:.1f}분")
    print("=" * 70)

    # 다음 단계 안내
    print("\n다음 단계 — auto_label.py:")
    print(
        f"  python bin_picking/src/labeling/auto_label.py \\\n"
        f"    --capture-dir {session_path} \\\n"
        f"    --part {part} \\\n"
        f"    --camera blaze-112 \\\n"
        f"    --output bin_picking/models/dataset_v1/"
    )
    print("\n→ ACCEPT 80%+ 면 자세 B/C 진행 / 미만이면 디버깅 (SOP v1.1 § 5.1)")

    return n_success


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="yaw sweep 캡처 세션 wrapper (SOP § 2.2 자동화)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 신규 세션
    p.add_argument("--part", type=str, help="부품 ID (stable_poses.yaml 키)")
    p.add_argument("--pose", type=str, help="안정 자세 ID (A/B/C/...)")
    p.add_argument("--light", type=str, default="normal", choices=["normal", "low", "side"])
    p.add_argument("--bg", type=str, default="white", choices=["white", "dark", "mixed"])
    p.add_argument("--yaw-step", type=int, default=15, help="yaw 간격 (도). SOP 기본 15°, 차원 축소 30°")
    p.add_argument("--yaw-start", type=int, default=0)
    p.add_argument("--yaw-end-exclusive", type=int, default=360)
    p.add_argument(
        "--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT,
        help="캡처 저장 루트 (기본: bin_picking/models/captures/)"
    )
    # 재개
    p.add_argument(
        "--resume", type=Path, default=None,
        help="기존 세션 디렉토리 (--part 등 무시, capture_session.json 사용)"
    )
    # 카메라 옵션
    p.add_argument("--ace2", action="store_true", help="ACE2 RGB 포함 (기본: --no-ace2)")
    # 자동 진행 (검증/테스트용, 일반 캡처는 안 씀)
    p.add_argument(
        "--auto-advance-after-sec", type=float, default=0.0,
        help="Enter 없이 N초 후 자동 캡처 (예: 5.0). 사람 회전대 돌리는 시간 확보용. 기본 0=대화형"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Blaze IP 환경변수 안내 (macOS 필수)
    if not os.environ.get("BASLER_BLAZE_IP"):
        print(
            "⚠️ BASLER_BLAZE_IP 환경변수 없음 (macOS 필수).\n"
            "   export BASLER_BLAZE_IP=192.168.20.10  먼저 실행 후 재시도.\n"
            "   (test_basler_live.py 호출 시 EnumerateDevices 실패할 수 있음)"
        )
        cont = input("그래도 진행? (y/N): ").strip().lower()
        if cont != "y":
            return 1

    # 세션 로드 또는 신규
    if args.resume:
        session_path = args.resume
        session = load_session(session_path)
        print(f"[resume] 기존 세션 로드: {session_path}")
    else:
        if not args.part or not args.pose:
            print("[ERROR] 신규 세션은 --part 와 --pose 필수 (또는 --resume <dir>)")
            return 1

        yaw_list = list(range(args.yaw_start, args.yaw_end_exclusive, args.yaw_step))
        if not yaw_list:
            print(f"[ERROR] yaw 리스트 비어있음 ({args.yaw_start}~{args.yaw_end_exclusive}, step {args.yaw_step})")
            return 1

        session_path = init_session(
            args.capture_root,
            args.part, args.pose, args.light, args.bg,
            yaw_list,
        )
        session = load_session(session_path)
        print(f"[new] 세션 생성: {session_path}")

    n_success = run_session(
        session_path,
        session,
        no_ace2=not args.ace2,
        auto_advance_after_sec=args.auto_advance_after_sec,
    )

    return 0 if n_success > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
