"""
프린터 어댑터 팩토리
====================
설정된 벤더에 맞는 PrinterAdapter 구현을 반환한다.
현재는 Formlabs 하나뿐이지만, FDM 등 새 벤더를 추가하면
여기에 분기만 추가하면 된다 (호출부는 그대로).

사용:
    adapter = await get_printer_adapter()   # settings.PRINTER_VENDOR 기본
"""

import logging
from typing import Optional

from app.core.config import get_settings
from app.adapters.base import PrinterAdapter
from app.services.formlabs_client import get_formlabs_client

logger = logging.getLogger(__name__)


async def get_printer_adapter(vendor: Optional[str] = None) -> PrinterAdapter:
    """벤더에 맞는 프린터 어댑터 반환.

    Args:
        vendor: 벤더 명시 (None이면 settings.PRINTER_VENDOR 사용).

    현재 지원: "formlabs" (SLA).
    향후: "prusa"/"octoprint" 등 FDM 어댑터를 elif로 추가.
    """
    settings = get_settings()
    vendor = (vendor or settings.PRINTER_VENDOR or "formlabs").lower()

    if vendor == "formlabs":
        return await get_formlabs_client()

    # 향후 FDM 등:
    # elif vendor == "prusa":
    #     return await get_prusa_adapter()

    raise ValueError(f"지원하지 않는 프린터 벤더: {vendor!r}")
