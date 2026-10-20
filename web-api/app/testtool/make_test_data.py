"""
시험항목 1 시험 데이터 생성기 — 셀A(세척기·경화기 상태 변경) + 셀B(빈피킹 인식 결과)
==================================================================================
SW 성능 시험(정량목표 2 · 통합 모니터링 응답속도 3초)의 시험 데이터 `events.json` 을 만든다.
한 번 만들어 SHA-256 을 규격서에 박으면 **바꾸지 않는다** (바꾸면 규격서·해시 잠금 테스트도 같이).

구성 (30건)
  · 셀A 18건 = 설비 4대(wash_1·wash_2·cure_1·cure_2)가 running → complete → idle 을 돌며 상태 변경
               같은 설비의 연속 이벤트는 반드시 상태가 바뀐다(서버는 변경만 전송) · 끝나면 4대 전부 idle(재실행 가능)
  · 셀B 12건 = 빈피킹 모듈이 서버에 보내는 인식 결과 payload — 🚨 지어낸 값이 아니라 **실물 인식 결과**(six.json)를
               `web_reporter.build_bin_picking_payload()` 로 변환한 것(운영 모듈이 보내는 형식 그대로)
               출처 = 9/4 OVN2 대조표 5장면(8/18 공장 촬영) · 9/16 팔 장착 Blaze 실물 2장면 · 10/12 공장 447mm 5장면
  · 순서 = [A, A, B, A, B] × 6 — 두 셀이 섞여 들어와도 화면이 각각 3초 안에 반영되는지 본다

사용:  cd web-api && venv/bin/python -m app.testtool.make_test_data [--out app/testtool/test_data_261020]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

WEB_API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = WEB_API_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from bin_picking.src.communication.web_reporter import build_bin_picking_payload  # noqa: E402

VERSION = "261020"
CAMERAS = {"wash_1": "wash", "wash_2": "wash", "cure_1": "cure", "cure_2": "cure"}
CYCLE = ("running", "complete", "idle")

# 셀B 실물 장면 12개 — (scene_id 접두, six.json 경로, 촬영·인식 시각 메모)
REAL_SCENES = [
    ("0904", "/data/jtm/e2e_reference_0904_OVN2/six/shot_001_c1.six.json", "2026-09-03T16:18:46"),
    ("0904", "/data/jtm/e2e_reference_0904_OVN2/six/shot_002_c1.six.json", "2026-09-03T16:18:48"),
    ("0904", "/data/jtm/e2e_reference_0904_OVN2/six/shot_003_c1.six.json", "2026-09-03T16:18:50"),
    ("0904", "/data/jtm/e2e_reference_0904_OVN2/six/shot_004_c1.six.json", "2026-09-03T16:19:02"),
    ("0904", "/data/jtm/e2e_reference_0904_OVN2/six/shot_005_c1.six.json", "2026-09-03T16:19:04"),
    ("0916", "/data/jtm/handover_0916/cap_0916/six/shot_001_c1_sA.six.json", "2026-09-16T12:57:00"),
    ("0916", "/data/jtm/handover_0916/cap_0916/six/live_20260916_122522.six.json", "2026-09-16T12:25:22"),
    ("1012", "/data/jtm/handover_1012/infer_view/six/shot_001_c1_sA.six.json", "2026-10-12T18:30:00"),
    ("1012", "/data/jtm/handover_1012/infer_view_roi/six/shot_001_c1_sA_roi.six.json", "2026-10-12T23:10:00"),
    ("1012", "/data/jtm/handover_1012/infer_view_roi2/six/shot_001_c1_sA_roi.six.json", "2026-10-12T23:20:00"),
    ("1012", "/data/jtm/handover_1012/infer_view_roi3/six/shot_001_c1_sA_roi.six.json", "2026-10-12T23:30:00"),
    ("1012", "/data/jtm/handover_1012/rehearsal_1012/infer/six/shot_001_c1_sA_roi.six.json", "2026-10-13T00:10:00"),
]


def cell_a_events(n: int = 18) -> list[dict]:
    """설비 4대 라운드로빈 · 각 설비는 running→complete→idle 순환. n은 12의 배수가 아니어도
    설비별로 3의 배수 건수가 되도록 배분해 끝 상태가 전부 idle 이 되게 한다."""
    per_cam = {c: 0 for c in CAMERAS}
    # 3건 단위로 설비에 배분 (18 = 6+6+3+3)
    cams = list(CAMERAS)
    blocks = n // 3
    for i in range(blocks):
        per_cam[cams[i % len(cams)]] += 3
    events: list[dict] = []
    state = {c: 0 for c in CAMERAS}  # CYCLE 인덱스
    remaining = dict(per_cam)
    while sum(remaining.values()) > 0:
        for cam in cams:
            if remaining[cam] == 0:
                continue
            st = CYCLE[state[cam] % 3]
            state[cam] += 1
            remaining[cam] -= 1
            events.append({"cell": "A", "kind": "vision", "camera_id": cam, "status": f"{CAMERAS[cam]}_{st}"})
    assert len(events) == n, len(events)
    # 끝 상태 검산
    last = {}
    for e in events:
        last[e["camera_id"]] = e["status"]
    for cam, st in last.items():
        if not st.endswith("_idle"):
            raise SystemExit(f"🔴 {cam} 끝 상태가 idle 이 아니다: {st}")
    return events


def cell_b_events() -> list[dict]:
    out: list[dict] = []
    for i, (tag, path, ts) in enumerate(REAL_SCENES, 1):
        p = Path(path)
        if not p.is_file():
            raise SystemExit(f"🔴 실물 six.json 없음: {p}")
        six = json.loads(p.read_text(encoding="utf-8"))
        payload = build_bin_picking_payload(six, latency_ms=None, timestamp=ts)
        payload["scene_id"] = f"cert_{tag}_{i:02d}_{six.get('scene_id') or p.stem}"
        # 운영 모듈이 보내는 그대로 — 좌표·각도·라벨·게이트 판정은 실물 값
        if not payload["detections"]:
            raise SystemExit(f"🔴 검출 0건 장면은 쓰지 않는다: {p}")
        out.append({"cell": "B", "kind": "binpick", "scene_id": payload["scene_id"], "report": payload})
    return out


def interleave(a: list[dict], b: list[dict]) -> list[dict]:
    """[A, A, B, A, B] 반복. 길이가 안 맞으면 남는 쪽을 뒤에 붙인다."""
    pattern = ("A", "A", "B", "A", "B")
    ia = ib = 0
    out: list[dict] = []
    while ia < len(a) or ib < len(b):
        for who in pattern:
            if who == "A" and ia < len(a):
                out.append(a[ia]); ia += 1
            elif who == "B" and ib < len(b):
                out.append(b[ib]); ib += 1
    for i, e in enumerate(out, 1):
        e["seq"] = i
        # seq 를 맨 앞에 두기 위해 재구성
    return [{"seq": e["seq"], **{k: v for k, v in e.items() if k != "seq"}} for e in out]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WEB_API_ROOT / "app" / "testtool" / f"test_data_{VERSION}"))
    a = ap.parse_args()
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    events = interleave(cell_a_events(18), cell_b_events())
    assert len(events) == 30, len(events)
    doc = {
        "name": "통합 모니터링 응답시간 시험 데이터 (시험항목 1 · 셀A 설비 상태 변경 + 셀B 빈피킹 인식 결과)",
        "version": VERSION,
        "precondition": "시험 시작 전 설비 4대(wash_1·wash_2·cure_1·cure_2) 상태를 idle 로 초기화 · 측정 페이지가 WebSocket 2개(/api/v1/vision/ws · /api/v1/binpick/ws)에 연결",
        "rule": "셀A: 같은 설비의 연속 이벤트는 반드시 상태가 바뀐다(running→complete→idle) · 셀B: 장면 ID 로 수신을 맞춘다 · 순서 = [A,A,B,A,B]×6",
        "source_cell_b": "실물 인식 결과(six.json)를 운영 모듈 web_reporter.build_bin_picking_payload 로 변환 — 9/4 OVN2 대조표 5 · 9/16 팔 장착 실물 2 · 10/12 공장 447mm 5",
        "counts": {"total": 30, "cell_a_vision": 18, "cell_b_binpick": 12},
        "events": events,
    }
    raw = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    path = out_dir / "events.json"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest().upper()
    print(f"✅ {path}  {len(raw):,} bytes  SHA-256 {digest}")
    print(f"   셀A {sum(e['cell']=='A' for e in events)} · 셀B {sum(e['cell']=='B' for e in events)} · 검출 합계 {sum(e['report']['summary']['n_detections'] for e in events if e['cell']=='B')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
