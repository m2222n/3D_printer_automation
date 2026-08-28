"""
Windows(cp949) 콘솔에서 이모지·한글 출력이 죽는 것을 막는다.

## 왜 필요한가 — 2026-08-28 IPC 실사고

IPC-510(Windows 11 **한글판**)에서 E2E 러너를 돌리자 **5/5 전부 실패**했다:

```
UnicodeEncodeError: 'cp949' codec can't encode character '⚠'
UnicodeEncodeError: 'cp949' codec can't encode character '\U0001f6e1'
```

- 리눅스(6000·A100)는 기본 인코딩이 **UTF-8**이라 이모지가 그냥 나간다
- **Windows 한글판은 `cp949`** 라 `⚠️`·`🛡️` 를 인코딩하지 못하고 **예외로 죽는다**

🚨 **추론은 성공했는데 "결과를 화면에 찍는 단계"에서 죽었다** = 조용히 틀리는 게 아니라
크게 실패한 것이라 바로 잡혔지만, **배포 대상이 Windows(IPC)** 이므로 근본 수정이 필요하다.

## 왜 print마다 이모지를 지우지 않았나

리포 전체에 이모지 print가 널려 있어 **하나씩 지우면 반드시 놓친다**(오늘도 파일 쓰기 2곳을
고친 뒤 print에서 또 터졌다). **stdout/stderr 자체를 UTF-8로 재설정**하는 것이 한 번에 끝난다.

⭐ 파일 쓰기는 별개다 — `write_text(..., encoding="utf-8")` 로 각 호출부에서 명시했다
(같은 날 4곳 수정). **이 모듈은 "화면 출력" 전용**이다.

## 쓰는 법

각 진입점(CLI) 최상단에서 한 번 호출한다:

```python
from bin_picking.src.utils.console_utf8 import enable_utf8_console
enable_utf8_console()
```

환경변수 `PYTHONUTF8=1` 로도 같은 효과를 얻지만, **셸 창을 닫으면 풀리고
서비스로 자동 실행할 때 빠진다.** 코드에 박아두면 실행 방식과 무관하게 동작한다.
"""

from __future__ import annotations

import sys


def enable_utf8_console() -> bool:
    """stdout/stderr 를 UTF-8 로 재설정한다.

    Returns:
        재설정을 실제로 수행했으면 True. 이미 UTF-8이거나 재설정이 불가능한
        환경(파이프로 리다이렉트된 특수 스트림 등)이면 False.

    🚨 **실패해도 예외를 던지지 않는다** — 이 함수는 부가 기능이고,
    여기서 죽으면 본 작업(추론·좌표 산출)이 통째로 멈춘다.
    `web_reporter` 의 *"보고 경로가 제어 경로처럼 굴면 안 된다"* 와 같은 원칙이다.
    """
    changed = False
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 파이썬 3.7+ 의 TextIOWrapper 가 아니면 건너뛴다
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue
        try:
            # errors="replace" = 그래도 못 찍는 문자가 있으면 죽지 말고 대체 문자로
            reconfigure(encoding="utf-8", errors="replace")
            changed = True
        except Exception:
            # 재설정 불가 환경은 그냥 둔다(이모지가 깨질 뿐 동작은 한다)
            pass
    return changed
