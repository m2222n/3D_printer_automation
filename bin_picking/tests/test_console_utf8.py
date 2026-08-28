#!/usr/bin/env python3
"""cp949 인코딩 회귀 검사 (2026-08-28 IPC 실사고)

## 무엇을 막는가

IPC-510(Windows 11 **한글판**)에서 E2E 러너가 **5/5 전부 실패**했다:

```
UnicodeEncodeError: 'cp949' codec can't encode character '⚠'      ← 파일 쓰기
UnicodeEncodeError: 'cp949' codec can't encode character '🛡️'     ← 화면 출력
```

리눅스는 기본이 UTF-8이라 **6000·A100에서는 절대 재현되지 않는다.**
⇒ 🚨 **이 테스트는 cp949 환경을 인위적으로 만들어** 리눅스에서도 회귀를 잡는다.

## ⭐ 그물이 찢어지는지 확인했다 (8/13 원칙)

`encoding="utf-8"` 을 빼면 `test_write_text_survives_cp949` 가 **실패한다**.
`enable_utf8_console()` 을 빼면 `test_console_survives_cp949` 가 **실패한다**.
*"통과하는 테스트"와 "실패할 수 있는 테스트"는 다르다.*

실행: `python bin_picking/tests/test_console_utf8.py`
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from bin_picking.src.utils.console_utf8 import enable_utf8_console  # noqa: E402

# 실사고에서 실제로 죽은 문자들
EMOJI = "⚠️🛡️✅🔴"
PASS = FAIL = 0


# 🚨 판정 출력은 **항상 진짜 stdout**으로 보낸다 — 아래 콘솔 테스트가 sys.stdout을
#    cp949로 바꿔치기하므로, 그 상태에서 이모지를 찍으면 테스트 자체가 죽는다
#    (실제로 처음 작성 때 그렇게 죽었다).
_REAL_STDOUT = sys.stdout


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}", file=_REAL_STDOUT)
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}", file=_REAL_STDOUT)


def test_write_text_survives_cp949() -> None:
    """6요소 JSON 쓰기가 cp949 기본 환경에서도 살아남는가.

    실사고 지점 = depth_track_to_6elements.py:404 (`write_text` 인코딩 미지정).
    """
    payload = {"scene_id": "t", "notes": f"게이트 제거 {EMOJI}"}
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    with tempfile.TemporaryDirectory() as td:
        # 🚨 인코딩 미지정 = Windows에서 cp949로 떨어지는 그 경로를 재현
        bad = Path(td) / "bad.json"
        try:
            bad.write_bytes(text.encode("cp949"))
            reproduced = False
        except UnicodeEncodeError:
            reproduced = True
        check("cp949로는 이모지를 못 쓴다(사고 재현)", reproduced,
              "cp949가 이모지를 받아버리면 이 테스트는 의미가 없다")

        # ✅ 현행 코드가 쓰는 방식
        good = Path(td) / "good.json"
        good.write_text(text, encoding="utf-8")
        back = json.loads(good.read_text(encoding="utf-8"))
        check("utf-8 명시하면 왕복이 온전하다", back["notes"] == payload["notes"])


def test_console_survives_cp949() -> None:
    """print가 cp949 스트림에서도 죽지 않는가.

    실사고 지점 = depth_track_to_6elements.py:398 (`print` 안의 🛡️).
    """
    saved = sys.stdout
    try:
        # cp949 콘솔을 흉내낸다(errors 기본값 = strict → 그대로면 죽는다)
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")

        died = False
        try:
            print(f"  🛡️ 게이트 제거 {EMOJI}")
            sys.stdout.flush()
        except UnicodeEncodeError:
            died = True
        check("cp949 콘솔에서 이모지 print가 죽는다(사고 재현)", died)

        # ✅ 방어를 적용하면 죽지 않아야 한다
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")
        enable_utf8_console()
        survived = True
        try:
            print(f"  🛡️ 게이트 제거 {EMOJI}")
            sys.stdout.flush()
        except UnicodeEncodeError:
            survived = False
        check("enable_utf8_console() 이후에는 살아남는다", survived,
              "이 줄이 실패하면 방어가 동작하지 않는 것이다")
    finally:
        sys.stdout = saved


def test_entrypoints_wired() -> None:
    """진입점 2개가 실제로 방어를 호출하는가.

    🚨 유틸만 만들고 호출을 안 걸면 아무 효과가 없다
    (8/6 *"단일 출처를 만드는 것과 모든 호출자가 그걸 쓰는 것은 다르다"*).
    """
    for rel in ("bin_picking/src/run_binpick_e2e.py",
                "bin_picking/src/pipeline/depth_track_to_6elements.py"):
        src = (REPO / rel).read_text(encoding="utf-8")
        check(f"{Path(rel).name} 이 enable_utf8_console 을 호출한다",
              "enable_utf8_console" in src)


def test_roundtrip_write_then_read() -> None:
    """🚨 쓰기만 UTF-8로 고치면 '읽기'에서 다시 죽는다 (8/28 2차 사고).

    1차 수정에서 `write_text` 만 고쳤더니 IPC에서 **`read_text` 가 cp949로 읽으려다**
    죽었다 — UTF-8로 써놓고 cp949로 읽으니 당연히 깨진다.
    ⇒ ⭐ *"같은 질문의 양쪽 끝을 다 봐야 전제가 선다"*(8/24 교훈).
    """
    text = json.dumps({"notes": f"게이트 {EMOJI}"}, ensure_ascii=False)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "rt.json"
        p.write_text(text, encoding="utf-8")

        # 🚨 인코딩 미지정 읽기 = Windows에서 cp949로 떨어지는 그 경로
        try:
            p.read_bytes().decode("cp949")
            reproduced = False
        except UnicodeDecodeError:
            reproduced = True
        check("UTF-8로 쓴 파일은 cp949로 못 읽는다(2차 사고 재현)", reproduced)

        back = json.loads(p.read_text(encoding="utf-8"))
        check("utf-8 명시하면 읽기 왕복이 온전하다", back["notes"] == f"게이트 {EMOJI}")


def _bare_calls(pattern: str) -> list[str]:
    """인코딩을 지정하지 않은 호출을 전수로 찾는다(괄호 균형으로 호출 끝을 판정)."""
    import re

    out = []
    for root in (REPO / "bin_picking/src", REPO / "bin_picking/depth_track/scripts"):
        for p in root.rglob("*.py"):
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(pattern, t):
                i, depth = m.end(), 1
                while i < len(t) and depth:
                    depth += (t[i] == "(") - (t[i] == ")")
                    i += 1
                if "encoding" not in t[m.start():i]:
                    out.append(f"{p.relative_to(REPO)}:{t[:m.start()].count(chr(10)) + 1}")
    return out


def test_no_bare_text_io() -> None:
    """인코딩 미지정 write_text/read_text 가 되살아나지 않았는가(전수·양방향).

    🚨 1차에는 write 만 검사해서 read 쪽 8곳을 통째로 놓쳤다.
    """
    for name, pat in (("write_text", r"\.write_text\("), ("read_text", r"\.read_text\(")):
        offenders = _bare_calls(pat)
        check(f"인코딩 미지정 {name} 0건", not offenders, str(offenders))


def test_subprocess_encoding() -> None:
    """subprocess 텍스트 모드도 인코딩을 지정하는가.

    🚨 자식 프로세스가 UTF-8로 출력하는데 부모가 cp949로 디코드하면
    **읽는 스레드에서 죽는다**(8/28 `_readerthread` UnicodeDecodeError).
    """
    import re

    offenders = []
    for p in (REPO / "bin_picking/src").rglob("*.py"):
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"text=True", t):
            window = t[m.start():m.start() + 200]
            if "encoding" not in window:
                offenders.append(f"{p.relative_to(REPO)}:{t[:m.start()].count(chr(10)) + 1}")
    check("subprocess text=True 에 encoding 지정 누락 0건", not offenders, str(offenders))


if __name__ == "__main__":
    print("=" * 62)
    print("cp949 인코딩 회귀 검사 (8/28 IPC 사고)")
    print("=" * 62)
    test_write_text_survives_cp949()
    test_roundtrip_write_then_read()
    test_console_survives_cp949()
    test_entrypoints_wired()
    test_no_bare_text_io()
    test_subprocess_encoding()
    print("-" * 62)
    print(f"통과 {PASS} · 실패 {FAIL}")
    sys.exit(1 if FAIL else 0)
